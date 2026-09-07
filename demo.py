import os
import sys
from face_processor import process_face
from reverse_search import reverse_image_search
from evidence_manager import (
    select_best_social_candidate,
    create_evidence_manifest,
    save_evidence,
    hash_evidence,
    build_merkle_evidence,
    compute_search_response_sha256,
)
from blockchain_client import (
    deploy_contract,
    attest_commitment,
    verify_evidence_on_chain,
)

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run_demo(image_path: str = "examples/demo.jpg"):
    print("==================================================")
    print("      FACETRACE: SOCIAL MEDIA PROVENANCE DEMO")
    print("==================================================")

    # [1/8] FACE SCAN
    print("\n[1/8] FACE SCAN")
    if not os.path.exists(image_path):
        print(f"      Error: Image not found at '{image_path}'")
        sys.exit(1)

    print(f"      Loading image: {image_path}")
    face_result = process_face(image_path)
    if not face_result["success"] or face_result["face_count"] != 1:
        print(f"      Error: {face_result['message']}")
        print("      DEMO IMAGE NOT SUITABLE FOR FACE PIPELINE")
        sys.exit(1)
    print(f"      Exactly one face detected.")

    # [2/8] FACE ENCODING
    print("\n[2/8] FACE ENCODING")
    source_img_hash = face_result["image_sha256"]
    face_enc_hash = face_result["embedding_sha256"]
    print(f"      Source-image SHA-256:   {source_img_hash}")
    print(f"      Facial-encoding SHA-256: {face_enc_hash}")
    print("      Note: Encoded 1434-D normalized facial landmark vector.")

    # [3/8] LIVE WEB SEARCH
    print("\n[3/8] LIVE WEB SEARCH")
    search_result = reverse_image_search(image_path, standalone=False)
    print(f"      SerpApi image upload:   SUCCEEDED")
    print(f"      Provider image_id:      {search_result['image_id']}")
    print(f"      Google Lens exact search: {search_result['exact_matches_count']} matches returned")

    # [4/8] SOCIAL POST DISCOVERY
    print("\n[4/8] SOCIAL POST DISCOVERY")
    candidates = search_result["social_candidates"]
    print(f"      Social candidates found: {len(candidates)}")
    selected = select_best_social_candidate(candidates)
    if not selected:
        print("      No viable social candidate found.")
        sys.exit(1)

    print(f"      Selected platform:       {selected['platform']}")
    print(f"      Selected URL:            {selected['url']}")
    print(f"      Provider position:       {selected['provider_position']}")
    print(f"      Selection explanation:   Selected via deterministic ranking (Tier 1 content post URL with earliest provider position).")

    # [5/8] EVIDENCE
    print("\n[5/8] EVIDENCE MANIFEST & CRYPTOGRAPHIC BINDING")
    if search_result["exact_social"]:
        search_type = "exact_matches"
        search_resp_path = search_result["exact_matches_file"]
    else:
        search_type = "visual_matches"
        search_resp_path = search_result["visual_matches_file"]
    search_resp_hash = compute_search_response_sha256(search_resp_path)
    evidence = create_evidence_manifest(
        source_image_sha256=source_img_hash,
        face_encoding_sha256=face_enc_hash,
        matched_candidate=selected,
        search_response_sha256=search_resp_hash,
        search_provider="google_lens_serpapi",
        search_type=search_type,
    )
    save_evidence(evidence, "output/evidence.json")
    evidence_hash = hash_evidence(evidence)
    print(f"      Search-response SHA-256: {search_resp_hash}")
    print(f"      Matched-post fingerprint:{evidence['matched_post_sha256']}")
    print(f"      Canonical evidence hash: {evidence_hash}")
    print("      Saved to: output/evidence.json")

    # [6/8] MERKLE PROVENANCE
    print("\n[6/8] MERKLE PROVENANCE")
    merkle_data = build_merkle_evidence(evidence, save_path="output/merkle_evidence.json")
    merkle_root = merkle_data["merkle_root"]
    print(f"      Merkle root generated:   {merkle_root}")
    print(f"      Leaves count:            {merkle_data['leaf_count']}")
    print("      Saved to: output/merkle_evidence.json")

    # [7/8] BLOCKCHAIN
    print("\n[7/8] BLOCKCHAIN ATTESTATION")
    dep = deploy_contract()
    print(f"      Registry contract:       {dep['contract_address']}")
    attest_res = attest_commitment(merkle_root)
    if attest_res["already_attested"]:
        print(f"      Status:                  ALREADY ATTESTED")
        print(f"      Attestation timestamp:   {attest_res['timestamp']}")
    else:
        print(f"      Attestation tx:          {attest_res['tx_hash']}")
        print(f"      Block number:            {attest_res['block_number']}")
        print(f"      Gas used:                {attest_res['gas_used']}")
    print(f"      On-chain commitment:     {merkle_root}")

    # [8/8] RE-VERIFICATION
    print("\n[8/8] RE-VERIFICATION & PROOFS")
    verify_res = verify_evidence_on_chain("output/evidence.json")
    for fld, ok in verify_res["proof_checks"].items():
        print(f"      Merkle proof [{fld}]: {'PASS' if ok else 'FAIL'}")
    print(f"      On-chain lookup:         {'PASS (FOUND)' if verify_res['on_chain_exists'] else 'FAIL'}")
    print(f"      Portable receipt:        {verify_res['receipt_file']}")

    if verify_res["verified"]:
        print("\n====================================")
        print("FACE → WEB → BLOCKCHAIN")
        print("END-TO-END VERIFICATION PASSED")
        print("====================================")
    else:
        print("\nVerification did not fully succeed.")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "examples/demo.jpg"
    run_demo(target)
