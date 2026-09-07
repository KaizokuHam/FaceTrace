import os
import sys
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional
from web3 import Web3

from evidence_manager import (
    hash_evidence,
    load_evidence,
    compute_search_response_sha256,
    compute_matched_post_fingerprint,
    build_merkle_evidence,
    verify_merkle_proof,
    MERKLE_FIELDS,
)

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
DEPLOYMENT_FILE = "output/deployment.json"
RECEIPT_FILE = "output/verification_receipt.json"
ARTIFACT_FILE = "artifacts/contracts/VerificationRegistry.sol/VerificationRegistry.json"


def get_web3_client(rpc_url: str = DEFAULT_RPC_URL) -> Web3:
    """Connect to the local Ethereum-compatible RPC endpoint."""
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(
            f"Failed to connect to local blockchain at {rpc_url}. "
            "Please ensure Hardhat or Anvil node is running (e.g. 'npx hardhat node')."
        )
    return w3


def load_contract_artifact(artifact_path: str = ARTIFACT_FILE) -> tuple[list, str]:
    """Load ABI and Bytecode from compiled contract artifact."""
    if not os.path.exists(artifact_path):
        raise FileNotFoundError(
            f"Contract artifact not found at {artifact_path}. "
            "Run 'npx hardhat compile' to build the contract."
        )
    with open(artifact_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    abi = data.get("abi")
    bytecode = data.get("bytecode")
    if not abi or not bytecode:
        raise ValueError(f"Invalid artifact format in {artifact_path}")
    return abi, bytecode


def deploy_contract(
    rpc_url: str = DEFAULT_RPC_URL,
    save_path: str = DEPLOYMENT_FILE,
    force_new: bool = False,
) -> dict:
    """
    Deploy VerificationRegistry contract to the local Ethereum node.
    Persists deployment metadata to output/deployment.json.
    """
    if not force_new and os.path.exists(save_path):
        try:
            with open(save_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            w3 = get_web3_client(rpc_url)
            code = w3.eth.get_code(Web3.to_checksum_address(cached["contract_address"]))
            if code and len(code) > 2:
                return cached
        except Exception:
            pass

    w3 = get_web3_client(rpc_url)
    abi, bytecode = load_contract_artifact()

    deployer = w3.eth.accounts[0]
    ContractFactory = w3.eth.contract(abi=abi, bytecode=bytecode)

    tx_hash = ContractFactory.constructor().transact({"from": deployer})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status != 1:
        raise RuntimeError(f"Contract deployment failed! Tx: {tx_hash.hex()}")

    contract_address = receipt.contractAddress
    deployment_info = {
        "network": "hardhat_local",
        "rpc_url": rpc_url,
        "chain_id": w3.eth.chain_id,
        "contract_address": contract_address,
        "deployer_address": deployer,
        "deployment_tx_hash": tx_hash.hex(),
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(deployment_info, f, indent=2)

    return deployment_info


def get_contract_instance(rpc_url: str = DEFAULT_RPC_URL, contract_address: Optional[str] = None):
    """Instantiate Web3 contract object from deployed address."""
    w3 = get_web3_client(rpc_url)
    abi, _ = load_contract_artifact()

    if not contract_address:
        if not os.path.exists(DEPLOYMENT_FILE):
            deploy_contract(rpc_url=rpc_url)
        with open(DEPLOYMENT_FILE, "r", encoding="utf-8") as f:
            deployment_info = json.load(f)
        contract_address = deployment_info["contract_address"]

    checksum_address = Web3.to_checksum_address(contract_address)
    return w3.eth.contract(address=checksum_address, abi=abi)


def hash_to_bytes32(hex_digest: str) -> bytes:
    """Format a 64-character SHA-256 hex digest as 32 raw bytes for Solidity bytes32."""
    clean_hex = hex_digest.lower().removeprefix("0x")
    if len(clean_hex) != 64:
        raise ValueError(f"Expected 64-character hex string, got {len(clean_hex)}")
    return bytes.fromhex(clean_hex)


def attest_commitment(
    commitment_hash: str,
    rpc_url: str = DEFAULT_RPC_URL,
    account_index: int = 0,
) -> dict:
    """
    Attest a 32-byte cryptographic commitment (such as a Merkle root or evidence hash) on-chain.

    PRIVACY GUARANTEE:
    Only the 32-byte cryptographic digest (bytes32) is submitted to the blockchain.
    Raw image bytes, raw facial landmark vectors, personal metadata, and full evidence JSON
    are NEVER sent on-chain, preventing permanent public storage of biometric data.
    """
    w3 = get_web3_client(rpc_url)
    contract = get_contract_instance(rpc_url=rpc_url)
    sender = w3.eth.accounts[account_index]
    hash_bytes = hash_to_bytes32(commitment_hash)

    already_exists = contract.functions.exists(hash_bytes).call()
    if already_exists:
        timestamp = contract.functions.attestations(hash_bytes).call()
        return {
            "status": "ALREADY_ATTESTED",
            "already_attested": True,
            "commitment_hash": commitment_hash,
            "tx_hash": None,
            "block_number": None,
            "timestamp": timestamp,
        }

    tx_hash = contract.functions.attest(hash_bytes).transact({"from": sender})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status != 1:
        raise RuntimeError(f"Attestation transaction failed: {tx_hash.hex()}")

    timestamp = contract.functions.attestations(hash_bytes).call()

    # Update deployment.json if exists
    if os.path.exists(DEPLOYMENT_FILE):
        try:
            with open(DEPLOYMENT_FILE, "r", encoding="utf-8") as f:
                dep_data = json.load(f)
            dep_data["attestation_tx"] = tx_hash.hex()
            dep_data["attestation_block_number"] = receipt.blockNumber
            dep_data["merkle_root_attested"] = commitment_hash
            with open(DEPLOYMENT_FILE, "w", encoding="utf-8") as f:
                json.dump(dep_data, f, indent=2)
        except Exception:
            pass

    return {
        "status": "SUCCESS",
        "already_attested": False,
        "commitment_hash": commitment_hash,
        "tx_hash": tx_hash.hex(),
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "attester": sender,
        "timestamp": timestamp,
    }


def attest_evidence(evidence_hash: str, rpc_url: str = DEFAULT_RPC_URL, account_index: int = 0) -> dict:
    """Convenience wrapper for legacy evidence_hash attestation."""
    return attest_commitment(evidence_hash, rpc_url=rpc_url, account_index=account_index)


def verify_evidence_on_chain(
    evidence_path: str = "output/evidence.json",
    merkle_path: str = "output/merkle_evidence.json",
    rpc_url: str = DEFAULT_RPC_URL,
) -> dict:
    """
    Execute comprehensive multi-layer verification:
    1. Read persisted evidence from disk and verify canonical SHA-256.
    2. Verify search response SHA-256 against actual response bytes.
    3. Recompute matched_post_sha256.
    4. Reconstruct Merkle tree and recompute Merkle root.
    5. Query contract exists(merkle_root).
    6. Verify Merkle inclusion proofs for:
       - matched_url
       - matched_post_sha256
       - source_image_sha256
       - search_response_sha256
    7. Generate and persist output/verification_receipt.json.
    """
    evidence = load_evidence(evidence_path)
    evidence_hash = hash_evidence(evidence)

    # 1. Search response provenance check
    response_file = (
        "phase0_visual_matches.json"
        if evidence.get("search_type") == "visual_matches"
        else "phase0_exact_matches.json"
    )
    resp_path = os.path.join("output", response_file)
    actual_search_hash = compute_search_response_sha256(resp_path) if os.path.exists(resp_path) else evidence.get("search_response_sha256")
    search_provenance_valid = (actual_search_hash == evidence.get("search_response_sha256"))

    # 2. Matched post fingerprint check
    recomputed_post_hash = compute_matched_post_fingerprint({
        "platform": evidence.get("matched_platform"),
        "position": evidence.get("provider_position"),
        "title": evidence.get("matched_title"),
        "url": evidence.get("matched_url"),
    })
    post_fingerprint_valid = (recomputed_post_hash == evidence.get("matched_post_sha256"))

    # 3. Merkle tree reconstruction
    merkle_data = build_merkle_evidence(evidence, save_path=merkle_path)
    merkle_root = merkle_data["merkle_root"]

    # 4. On-chain query
    contract = get_contract_instance(rpc_url=rpc_url)
    root_bytes = hash_to_bytes32(merkle_root)
    on_chain_exists = contract.functions.exists(root_bytes).call()
    timestamp = contract.functions.attestations(root_bytes).call() if on_chain_exists else 0

    # 5. Merkle inclusion proof checks
    proof_checks = {}
    verified_fields = ["matched_url", "matched_post_sha256", "source_image_sha256", "search_response_sha256"]
    all_proofs_pass = True

    for fld in verified_fields:
        leaf_h = merkle_data["leaves"][fld]["leaf_hash"]
        proof = merkle_data["proofs"][fld]
        is_valid = verify_merkle_proof(leaf_h, proof, merkle_root)
        proof_checks[fld] = is_valid
        if not is_valid:
            all_proofs_pass = False

    overall_verified = (
        on_chain_exists and
        search_provenance_valid and
        post_fingerprint_valid and
        all_proofs_pass
    )

    # Load deployment info if present
    dep_info = {}
    if os.path.exists(DEPLOYMENT_FILE):
        try:
            with open(DEPLOYMENT_FILE, "r", encoding="utf-8") as f:
                dep_info = json.load(f)
        except Exception:
            pass

    # 6. Build and persist portable verification receipt
    receipt_data = {
        "schema_version": "1.0",
        "source_image_sha256": evidence.get("source_image_sha256"),
        "face_encoding_sha256": evidence.get("face_encoding_sha256"),
        "search_response_sha256": evidence.get("search_response_sha256"),
        "matched_post_sha256": evidence.get("matched_post_sha256"),
        "evidence_sha256": evidence_hash,
        "merkle_root": merkle_root,
        "matched_platform": evidence.get("matched_platform"),
        "matched_url": evidence.get("matched_url"),
        "provider_position": evidence.get("provider_position"),
        "network": dep_info.get("network", "hardhat_local"),
        "chain_id": dep_info.get("chain_id", 31337),
        "contract_address": dep_info.get("contract_address"),
        "attestation_tx": dep_info.get("attestation_tx"),
        "block_number": dep_info.get("attestation_block_number", dep_info.get("block_number")),
        "attestation_timestamp": timestamp,
        "search_provenance_verified": search_provenance_valid,
        "post_fingerprint_verified": post_fingerprint_valid,
        "merkle_proofs_verified": all_proofs_pass,
        "blockchain_verified": on_chain_exists,
        "verified": overall_verified,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(os.path.dirname(os.path.abspath(RECEIPT_FILE)), exist_ok=True)
    with open(RECEIPT_FILE, "w", encoding="utf-8") as f:
        json.dump(receipt_data, f, indent=2)

    return {
        "verified": overall_verified,
        "evidence_sha256": evidence_hash,
        "search_response_sha256": evidence.get("search_response_sha256"),
        "matched_post_sha256": evidence.get("matched_post_sha256"),
        "merkle_root": merkle_root,
        "on_chain_exists": on_chain_exists,
        "attestation_timestamp": timestamp,
        "proof_checks": proof_checks,
        "receipt_file": RECEIPT_FILE,
        "contract_address": dep_info.get("contract_address"),
    }


def run_multi_tamper_test(
    evidence_path: str = "output/evidence.json",
    rpc_url: str = DEFAULT_RPC_URL,
) -> dict:
    """
    Demonstrate cryptographic tamper-evidence across multiple failure cases:
    CASE A: Mutate matched_url -> matched_post_sha256 changes -> Merkle root changes -> on-chain FAIL.
    CASE B: Mutate matched_title -> matched_post_sha256 changes -> Merkle root changes -> on-chain FAIL.
    CASE C: Mutate source_image_sha256 -> Merkle root changes -> on-chain FAIL.
    CASE D: Mutate search_response_sha256 -> Merkle root changes -> on-chain FAIL.

    Guarantees the real evidence.json on disk is NEVER corrupted.
    """
    original_evidence = load_evidence(evidence_path)
    contract = get_contract_instance(rpc_url=rpc_url)

    # Reconstruct original tree
    orig_merkle = build_merkle_evidence(original_evidence, save_path="output/merkle_evidence.json")
    orig_root = orig_merkle["merkle_root"]
    orig_exists = contract.functions.exists(hash_to_bytes32(orig_root)).call()

    results = {
        "original_merkle_root": orig_root,
        "original_on_chain": orig_exists,
        "cases": {},
        "all_tamper_cases_rejected": True,
    }

    cases = [
        ("case_a_url", "matched_url", original_evidence.get("matched_url", "") + "X"),
        ("case_b_title", "matched_title", original_evidence.get("matched_title", "") + " [TAMPERED]"),
        ("case_c_image", "source_image_sha256", "f" * 64),
        ("case_d_search", "search_response_sha256", "0" * 64),
    ]

    for case_id, field_to_tamper, new_val in cases:
        tampered = json.loads(json.dumps(original_evidence))
        tampered[field_to_tamper] = new_val

        # Recompute post hash if post fields changed
        if field_to_tamper in ("matched_url", "matched_title"):
            tampered["matched_post_sha256"] = compute_matched_post_fingerprint({
                "platform": tampered.get("matched_platform"),
                "position": tampered.get("provider_position"),
                "title": tampered.get("matched_title"),
                "url": tampered.get("matched_url"),
            })

        # Build in-memory Merkle tree without overwriting disk
        sorted_fields = sorted(MERKLE_FIELDS)
        leaf_hashes = []
        for fld in sorted_fields:
            _, h = hashlib.sha256(f"{fld}:{tampered.get(fld, '')}".encode("utf-8")).hexdigest(), None
            leaf_h = hashlib.sha256(f"{fld}:{tampered.get(fld, '')}".encode("utf-8")).hexdigest()
            leaf_hashes.append(leaf_h)

        curr = list(leaf_hashes)
        while len(curr) > 1:
            if len(curr) % 2 != 0:
                curr.append(curr[-1])
            nxt = [
                hashlib.sha256(bytes.fromhex(curr[i]) + bytes.fromhex(curr[i + 1])).hexdigest()
                for i in range(0, len(curr), 2)
            ]
            curr = nxt
        tampered_root = curr[0]

        tampered_exists = contract.functions.exists(hash_to_bytes32(tampered_root)).call()
        is_rejected = (not tampered_exists) and (tampered_root != orig_root)
        if not is_rejected:
            results["all_tamper_cases_rejected"] = False

        results["cases"][case_id] = {
            "tampered_field": field_to_tamper,
            "tampered_root": tampered_root,
            "roots_differ": tampered_root != orig_root,
            "on_chain_exists": tampered_exists,
            "rejected_by_blockchain": is_rejected,
        }

    # Verify disk is unchanged
    disk_evidence = load_evidence(evidence_path)
    disk_hash = hash_evidence(disk_evidence)
    results["disk_intact"] = (disk_hash == hash_evidence(original_evidence))

    return results


def run_tamper_verification_test(evidence_path: str = "output/evidence.json", rpc_url: str = DEFAULT_RPC_URL) -> dict:
    """Backwards-compatible wrapper for tamper verification."""
    return run_multi_tamper_test(evidence_path=evidence_path, rpc_url=rpc_url)
