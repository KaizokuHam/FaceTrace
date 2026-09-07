import argparse
import json
import os
import platform
import statistics
import subprocess
import tempfile
import time
from importlib import metadata
from pathlib import Path

import cv2
import serpapi
from dotenv import load_dotenv
from PIL import Image

from blockchain_client import (
    SEPOLIA_DEPLOYMENT_FILE,
    attest_commitment,
    deploy_contract,
    get_sepolia_preflight,
    verify_evidence_on_chain,
)
from evidence_manager import (
    MERKLE_FIELDS,
    build_merkle_evidence,
    compute_matched_post_fingerprint,
    compute_search_response_sha256,
    create_evidence_manifest,
    hash_evidence,
    rank_and_score_candidates,
    verify_merkle_proof,
)
from face_processor import (
    compute_embedding_sha256,
    compute_file_sha256,
    detect_faces,
    extract_face_embedding,
    process_face,
)
from reverse_search import (
    extract_social_candidates,
    get_match_items,
    validate_image_file,
)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _summarize_ms(samples: list[float]) -> dict:
    return {
        "runs": len(samples),
        "mean_ms": round(statistics.fmean(samples), 3),
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(_percentile(samples, 0.95), 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
    }


def _measure(function, runs: int, warmup: int = 2) -> dict:
    for _ in range(warmup):
        function()
    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1000)
    return _summarize_ms(samples)


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def benchmark_environment(image_path: str) -> dict:
    with Image.open(image_path) as image:
        dimensions = [image.width, image.height]
    try:
        node_version = subprocess.run(
            ["node", "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        node_version = "not captured"
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "node": node_version,
        "cpu": os.getenv("PROCESSOR_IDENTIFIER") or platform.processor() or "not captured",
        "architecture": platform.machine(),
        "image_dimensions_px": dimensions,
        "image_size_bytes": os.path.getsize(image_path),
        "packages": {
            "mediapipe": _package_version("mediapipe"),
            "numpy": _package_version("numpy"),
            "opencv-python": _package_version("opencv-python"),
            "Pillow": _package_version("Pillow"),
            "serpapi": _package_version("serpapi"),
            "web3": _package_version("web3"),
        },
    }


def benchmark_face(image_path: str, runs: int) -> dict:
    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        raise ValueError(f"Unable to read benchmark image: {image_path}")
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    encoding = extract_face_embedding(image_rgb)
    return {
        "image_validation": _measure(lambda: validate_image_file(image_path), runs),
        "face_detection": _measure(lambda: detect_faces(image_rgb), runs),
        "landmark_encoding": _measure(lambda: extract_face_embedding(image_rgb), runs),
        "image_sha256": _measure(lambda: compute_file_sha256(image_path), runs),
        "encoding_sha256": _measure(lambda: compute_embedding_sha256(encoding), runs),
        "full_face_processing": _measure(lambda: process_face(image_path), runs),
    }


def _candidate_from_evidence(evidence: dict) -> dict:
    return {
        "platform": evidence["matched_platform"],
        "url": evidence["matched_url"],
        "title": evidence["matched_title"],
        "position": evidence["provider_position"],
    }


def benchmark_evidence(
    evidence: dict,
    response_path: str,
    candidates: list[dict],
    runs: int,
    temp_dir: str,
) -> dict:
    candidate = _candidate_from_evidence(evidence)
    ranking_path = os.path.join(temp_dir, "ranked.json")
    merkle_path = os.path.join(temp_dir, "merkle.json")
    stable_created_at = evidence.get("created_at", "benchmark")

    def create_manifest():
        return create_evidence_manifest(
            evidence["source_image_sha256"],
            evidence["face_encoding_sha256"],
            candidate,
            evidence["search_response_sha256"],
            evidence["search_provider"],
            evidence["search_type"],
            stable_created_at,
        )

    merkle = build_merkle_evidence(evidence, merkle_path)

    def verify_proofs():
        for field in MERKLE_FIELDS:
            leaf = merkle["leaves"][field]["leaf_hash"]
            if not verify_merkle_proof(leaf, merkle["proofs"][field], merkle["merkle_root"]):
                raise RuntimeError(f"Merkle proof failed during benchmark: {field}")

    def complete_stage():
        ranked = rank_and_score_candidates(candidates, ranking_path)
        manifest = create_evidence_manifest(
            evidence["source_image_sha256"],
            evidence["face_encoding_sha256"],
            ranked[0],
            evidence["search_response_sha256"],
            evidence["search_provider"],
            evidence["search_type"],
            stable_created_at,
        )
        hash_evidence(manifest)
        tree = build_merkle_evidence(manifest, merkle_path)
        field = "matched_url"
        if not verify_merkle_proof(
            tree["leaves"][field]["leaf_hash"],
            tree["proofs"][field],
            tree["merkle_root"],
        ):
            raise RuntimeError("Complete evidence-stage proof verification failed.")

    ranking_runs = min(runs, 100)
    return {
        "candidate_ranking": _measure(
            lambda: rank_and_score_candidates(candidates, ranking_path),
            ranking_runs,
        ),
        "search_response_sha256": _measure(
            lambda: compute_search_response_sha256(response_path),
            runs,
        ),
        "matched_post_fingerprint": _measure(
            lambda: compute_matched_post_fingerprint(candidate),
            runs,
        ),
        "evidence_manifest": _measure(create_manifest, runs),
        "evidence_sha256": _measure(lambda: hash_evidence(evidence), runs),
        "merkle_construction": _measure(
            lambda: build_merkle_evidence(evidence, merkle_path),
            runs,
        ),
        "merkle_proof_verification_all_leaves": _measure(verify_proofs, runs),
        "complete_evidence_provenance": _measure(complete_stage, ranking_runs),
    }


def benchmark_local_blockchain(
    response_path: str,
    merkle_root: str,
    runs: int,
    temp_dir: str,
) -> dict:
    deployment_samples = []
    attestation_samples = []
    verification_samples = []
    deployment_gas = []
    attestation_gas = []

    for index in range(runs):
        deployment_path = os.path.join(temp_dir, f"deployment-{index}.json")
        receipt_path = os.path.join(temp_dir, f"receipt-{index}.json")
        merkle_path = os.path.join(temp_dir, f"chain-merkle-{index}.json")

        started = time.perf_counter()
        deployment = deploy_contract(save_path=deployment_path, force_new=True)
        deployment_samples.append((time.perf_counter() - started) * 1000)
        deployment_gas.append(deployment["gas_used"])

        started = time.perf_counter()
        attestation = attest_commitment(
            merkle_root,
            deployment_path=deployment_path,
        )
        attestation_samples.append((time.perf_counter() - started) * 1000)
        attestation_gas.append(attestation["gas_used"])

        started = time.perf_counter()
        verification = verify_evidence_on_chain(
            evidence_path="output/evidence.json",
            merkle_path=merkle_path,
            deployment_path=deployment_path,
            receipt_path=receipt_path,
            search_response_path=response_path,
        )
        verification_samples.append((time.perf_counter() - started) * 1000)
        if not verification["verified"]:
            raise RuntimeError("Local blockchain verification failed during benchmark.")

    return {
        "deployment_latency": _summarize_ms(deployment_samples),
        "attestation_latency": _summarize_ms(attestation_samples),
        "verification_read_latency": _summarize_ms(verification_samples),
        "deployment_gas_used": sorted(set(deployment_gas)),
        "attestation_gas_used": sorted(set(attestation_gas)),
        "chain_id": 31337,
    }


def benchmark_local_replay_end_to_end(
    image_path: str,
    response_path: str,
    response: dict,
    search_type: str,
    temp_dir: str,
) -> dict:
    started = time.perf_counter()
    face = process_face(image_path)
    if not face["success"]:
        raise RuntimeError(face["message"])
    candidates = extract_social_candidates(get_match_items(response, search_type))
    ranked = rank_and_score_candidates(
        candidates,
        os.path.join(temp_dir, "replay-ranked.json"),
    )
    evidence = create_evidence_manifest(
        face["image_sha256"],
        face["embedding_sha256"],
        ranked[0],
        compute_search_response_sha256(response_path),
        "google_lens_serpapi",
        search_type,
    )
    evidence_path = os.path.join(temp_dir, "replay-evidence.json")
    _write_live_evidence(evidence_path, evidence)
    merkle = build_merkle_evidence(
        evidence,
        os.path.join(temp_dir, "replay-merkle.json"),
    )
    deployment_path = os.path.join(temp_dir, "replay-deployment.json")
    deploy_contract(save_path=deployment_path, force_new=True)
    attest_commitment(merkle["merkle_root"], deployment_path=deployment_path)
    verification = verify_evidence_on_chain(
        evidence_path=evidence_path,
        merkle_path=os.path.join(temp_dir, "replay-verify-merkle.json"),
        deployment_path=deployment_path,
        receipt_path=os.path.join(temp_dir, "replay-receipt.json"),
        search_response_path=response_path,
    )
    if not verification["verified"]:
        raise RuntimeError("Local replay end-to-end verification failed.")
    return {
        "runs": 1,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "search_input": "saved real provider response",
        "external_upload_and_search_latency": "excluded",
        "verified": True,
    }


def benchmark_live_end_to_end(image_path: str, temp_dir: str) -> dict:
    load_dotenv()
    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SERPAPI_API_KEY is required for --live.")
    client = serpapi.Client(api_key=api_key)

    total_started = time.perf_counter()
    face = process_face(image_path)
    if not face["success"]:
        raise RuntimeError(face["message"])

    upload_started = time.perf_counter()
    upload_response = client.upload_image(image_path)
    upload_ms = (time.perf_counter() - upload_started) * 1000
    image_id = upload_response.get("image_id") if isinstance(upload_response, dict) else None
    if not image_id:
        raise RuntimeError("Live benchmark image upload did not return an image ID.")

    lens_started = time.perf_counter()
    search_requests = 1
    search_type = "exact_matches"
    response = client.search({
        "engine": "google_lens",
        "image_id": image_id,
        "type": search_type,
        "no_cache": True,
    })
    response_data = response.as_dict() if hasattr(response, "as_dict") else dict(response)
    items = get_match_items(response_data, search_type)
    candidates = extract_social_candidates(items)

    if not candidates:
        search_requests += 1
        search_type = "visual_matches"
        response = client.search({
            "engine": "google_lens",
            "image_id": image_id,
            "type": search_type,
            "no_cache": True,
        })
        response_data = response.as_dict() if hasattr(response, "as_dict") else dict(response)
        items = get_match_items(response_data, search_type)
        candidates = extract_social_candidates(items)
    lens_ms = (time.perf_counter() - lens_started) * 1000

    if not candidates:
        raise RuntimeError("Live benchmark returned no social candidates.")
    response_path = os.path.join(temp_dir, f"live-{search_type}.json")
    with open(response_path, "w", encoding="utf-8") as f:
        json.dump(response_data, f, indent=2)
    ranked = rank_and_score_candidates(candidates, os.path.join(temp_dir, "live-ranked.json"))
    selected = ranked[0]
    response_hash = compute_search_response_sha256(response_path)
    evidence = create_evidence_manifest(
        face["image_sha256"],
        face["embedding_sha256"],
        selected,
        response_hash,
        "google_lens_serpapi",
        search_type,
    )
    live_evidence_path = os.path.join(temp_dir, "live-evidence.json")
    _write_live_evidence(live_evidence_path, evidence)
    hash_evidence(evidence)
    merkle = build_merkle_evidence(evidence, os.path.join(temp_dir, "live-merkle.json"))

    deployment_path = os.path.join(temp_dir, "live-deployment.json")
    receipt_path = os.path.join(temp_dir, "live-receipt.json")
    deployment = deploy_contract(save_path=deployment_path, force_new=True)
    attestation = attest_commitment(
        merkle["merkle_root"],
        deployment_path=deployment_path,
    )
    verification = verify_evidence_on_chain(
        evidence_path=live_evidence_path,
        merkle_path=os.path.join(temp_dir, "live-verify-merkle.json"),
        deployment_path=deployment_path,
        receipt_path=receipt_path,
        search_response_path=response_path,
    )
    total_ms = (time.perf_counter() - total_started) * 1000

    return {
        "search_requests": search_requests,
        "search_type": search_type,
        "upload_latency_ms": round(upload_ms, 1),
        "lens_latency_ms": round(lens_ms, 1),
        "total_search_latency_ms": round(upload_ms + lens_ms, 1),
        "result_count": len(items),
        "social_candidate_count": len(candidates),
        "selected_platform": selected["platform"],
        "local_deployment_gas_used": deployment["gas_used"],
        "local_attestation_gas_used": attestation["gas_used"],
        "verified": verification["verified"],
        "end_to_end_latency_ms": round(total_ms, 1),
    }


def _write_live_evidence(path: str, evidence: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)


def read_sepolia_receipts() -> dict:
    deployment_path = Path(SEPOLIA_DEPLOYMENT_FILE)
    if not deployment_path.exists():
        return {"status": "not captured"}
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    result = {
        "network": "Ethereum Sepolia",
        "chain_id": deployment.get("chain_id"),
        "deployment_block": deployment.get("deployment_block"),
        "attestation_block": deployment.get("attestation_block"),
        "deployment_gas_used": deployment.get("gas_used"),
        "attestation_gas_used": deployment.get("attestation_gas_used"),
        "confirmation_latency": "not captured",
    }
    try:
        preflight = get_sepolia_preflight(require_private_key=False)
        if deployment.get("deployment_tx"):
            receipt = preflight["w3"].eth.get_transaction_receipt(deployment["deployment_tx"])
            result["deployment_gas_used"] = receipt.gasUsed
        if deployment.get("attestation_tx"):
            receipt = preflight["w3"].eth.get_transaction_receipt(deployment["attestation_tx"])
            result["attestation_gas_used"] = receipt.gasUsed
    except Exception:
        pass
    return result


def read_existing_search_measurement(response: dict, candidates: list[dict]) -> dict:
    metadata_section = response.get("search_metadata", {})
    provider_seconds = metadata_section.get("total_time_taken")
    return {
        "source": "saved real SerpApi Google Lens response",
        "captured_at_utc": metadata_section.get("created_at", "not captured"),
        "provider_processing_ms": (
            round(float(provider_seconds) * 1000, 1)
            if provider_seconds is not None
            else "not captured"
        ),
        "client_upload_latency": "not captured",
        "client_round_trip_latency": "not captured",
        "social_candidate_count": len(candidates),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Measure FaceTrace performance.")
    parser.add_argument("image", nargs="?", default="examples/demo.jpg")
    parser.add_argument("--face-runs", type=int, default=20)
    parser.add_argument("--crypto-runs", type=int, default=200)
    parser.add_argument("--blockchain-runs", type=int, default=3)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use one live upload and at most two Lens queries; consumes provider quota.",
    )
    parser.add_argument("--output", default="output/benchmark_results.json")
    return parser.parse_args()


def main():
    args = parse_args()
    image_path = validate_image_file(args.image)
    evidence = json.loads(Path("output/evidence.json").read_text(encoding="utf-8"))
    response_name = (
        "phase0_visual_matches.json"
        if evidence.get("search_type") == "visual_matches"
        else "phase0_exact_matches.json"
    )
    response_path = os.path.join("output", response_name)
    response = json.loads(Path(response_path).read_text(encoding="utf-8"))
    candidates = extract_social_candidates(get_match_items(response, evidence["search_type"]))

    with tempfile.TemporaryDirectory(prefix="facetrace-benchmark-") as temp_dir:
        results = {
            "environment": benchmark_environment(image_path),
            "methodology": {
                "warmup_runs": 2,
                "face_measured_runs": args.face_runs,
                "crypto_measured_runs": args.crypto_runs,
                "local_blockchain_runs": args.blockchain_runs,
                "live_search_runs": 1 if args.live else 0,
            },
            "face": benchmark_face(image_path, args.face_runs),
            "evidence": benchmark_evidence(
                evidence,
                response_path,
                candidates,
                args.crypto_runs,
                temp_dir,
            ),
            "existing_search_measurement": read_existing_search_measurement(
                response,
                candidates,
            ),
        }
        merkle = build_merkle_evidence(evidence, os.path.join(temp_dir, "base-merkle.json"))
        results["local_blockchain"] = benchmark_local_blockchain(
            response_path,
            merkle["merkle_root"],
            args.blockchain_runs,
            temp_dir,
        )
        results["local_replay_end_to_end"] = benchmark_local_replay_end_to_end(
            image_path,
            response_path,
            response,
            evidence["search_type"],
            temp_dir,
        )
        if args.live:
            results["live_search_and_end_to_end"] = benchmark_live_end_to_end(
                image_path,
                temp_dir,
            )
        results["sepolia"] = read_sepolia_receipts()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"Benchmark results saved to: {output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Benchmark failed ({type(exc).__name__}).")
        raise SystemExit(1)
