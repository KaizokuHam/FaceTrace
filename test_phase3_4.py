import os
import sys
import json
import tempfile
import hashlib
from web3 import Web3

from evidence_manager import (
    canonicalize_evidence,
    hash_evidence,
    save_evidence,
    load_evidence,
    create_evidence_manifest,
)
from blockchain_client import (
    get_web3_client,
    deploy_contract,
    attest_evidence,
    verify_evidence_on_chain,
    run_tamper_verification_test,
    hash_to_bytes32,
    get_contract_instance,
)

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def test_canonical_json_order_determinism():
    """1. Verify that dictionary key insertion order does not alter canonical serialization."""
    d1 = {
        "version": "1.0",
        "matched_url": "https://x.com/post/123",
        "provider_position": 5,
        "source_image_sha256": "aaaa1111",
        "face_encoding_sha256": "bbbb2222",
    }
    d2 = {
        "face_encoding_sha256": "bbbb2222",
        "source_image_sha256": "aaaa1111",
        "version": "1.0",
        "provider_position": 5,
        "matched_url": "https://x.com/post/123",
    }

    b1 = canonicalize_evidence(d1)
    b2 = canonicalize_evidence(d2)
    assert b1 == b2, "Canonical bytes must be identical regardless of key order"


def test_same_evidence_same_hash():
    """2. Verify that identical evidence dictionaries produce the exact same SHA-256 digest."""
    d1 = {
        "version": "1.0",
        "source_image_sha256": "1234567890abcdef",
        "matched_url": "https://x.com/sample/1",
        "created_at": "2026-09-07T10:00:00+00:00",
    }
    d2 = dict(d1)

    h1 = hash_evidence(d1)
    h2 = hash_evidence(d2)
    assert h1 == h2, f"Hashes must match: {h1} vs {h2}"
    assert len(h1) == 64


def test_changed_matched_url_different_hash():
    """3. Verify that changing matched_url by even a single character changes the digest."""
    orig = {
        "version": "1.0",
        "matched_url": "https://x.com/status/12345678",
        "created_at": "2026-09-07T10:00:00+00:00",
    }
    tampered = dict(orig)
    tampered["matched_url"] = "https://x.com/status/12345679"

    h_orig = hash_evidence(orig)
    h_tampered = hash_evidence(tampered)
    assert h_orig != h_tampered, "Digest must differ when matched_url is altered"


def test_saved_and_loaded_evidence_same_hash():
    """4. Verify that saving to disk and loading produces an identical canonical hash."""
    sample = {
        "version": "1.0",
        "source_image_sha256": "d2d0839f73aaf58d93210c8fdba16c38ffc0d644a9c3fdfc5a18a4e8f230f8f8",
        "face_encoding_sha256": "f12ad982d0a1d1f757d65d6db4556639ea003b1ec7056f396cfddd4f210f6667",
        "matched_url": "https://x.com/example/status/1234567890",
        "created_at": "2026-09-07T05:34:42.072008+00:00",
    }

    orig_hash = hash_evidence(sample)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_path = tf.name

    try:
        save_evidence(sample, temp_path)
        loaded = load_evidence(temp_path)
        loaded_hash = hash_evidence(loaded)
        assert orig_hash == loaded_hash, f"Loaded hash {loaded_hash} != original hash {orig_hash}"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_contract_deployment_succeeds():
    """5. Verify that VerificationRegistry deploys to local Hardhat node."""
    w3 = get_web3_client()
    dep = deploy_contract()
    addr = dep["contract_address"]
    assert Web3.is_address(addr), f"Invalid contract address: {addr}"

    code = w3.eth.get_code(Web3.to_checksum_address(addr))
    assert len(code) > 2, "Contract bytecode not found at deployed address"


def test_evidence_attestation_transaction_succeeds():
    """6. Verify that an evidence hash can be attested via live transaction."""
    # Generate unique test hash
    unique_test_data = {"test_run": os.urandom(16).hex()}
    test_hash = hash_evidence(unique_test_data)

    res = attest_evidence(test_hash)
    assert res["status"] == "SUCCESS"
    assert res["tx_hash"] is not None
    assert res["block_number"] is not None
    assert res["timestamp"] > 0


def test_exists_original_hash_true():
    """7. Verify that exists(original_hash) returns true on-chain."""
    unique_test_data = {"unique_entity": os.urandom(16).hex()}
    test_hash = hash_evidence(unique_test_data)
    attest_evidence(test_hash)

    contract = get_contract_instance()
    hash_bytes = hash_to_bytes32(test_hash)
    exists = contract.functions.exists(hash_bytes).call()
    assert exists is True, "Expected exists(test_hash) to be True"


def test_exists_tampered_hash_false():
    """8. Verify that an unattested / tampered hash returns false on-chain."""
    unattested_hash = hashlib.sha256(b"unattested_random_string_xyz_999").hexdigest()
    contract = get_contract_instance()
    hash_bytes = hash_to_bytes32(unattested_hash)
    exists = contract.functions.exists(hash_bytes).call()
    assert exists is False, "Expected exists(unattested_hash) to be False"


def test_duplicate_attestation_behaves_as_intended():
    """9. Verify that duplicate attestation behaves safely and is rejected/handled."""
    unique_test_data = {"duplicate_test": os.urandom(16).hex()}
    test_hash = hash_evidence(unique_test_data)

    # First attestation succeeds
    r1 = attest_evidence(test_hash)
    assert r1["status"] == "SUCCESS"

    # Second attestation detected as already attested
    r2 = attest_evidence(test_hash)
    assert r2["already_attested"] is True
    assert r2["timestamp"] == r1["timestamp"]


if __name__ == "__main__":
    print("Running Phase 3 & 4 Automated Test Suite...")

    test_canonical_json_order_determinism()
    print("  [PASS] 1. canonical JSON order determinism")

    test_same_evidence_same_hash()
    print("  [PASS] 2. same evidence -> same hash")

    test_changed_matched_url_different_hash()
    print("  [PASS] 3. changed matched_url -> different hash")

    test_saved_and_loaded_evidence_same_hash()
    print("  [PASS] 4. saved + loaded evidence -> same hash")

    test_contract_deployment_succeeds()
    print("  [PASS] 5. contract deployment succeeds")

    test_evidence_attestation_transaction_succeeds()
    print("  [PASS] 6. evidence attestation transaction succeeds")

    test_exists_original_hash_true()
    print("  [PASS] 7. exists(original_hash) == true")

    test_exists_tampered_hash_false()
    print("  [PASS] 8. exists(tampered_hash) == false")

    test_duplicate_attestation_behaves_as_intended()
    print("  [PASS] 9. duplicate attestation behaves as intended")

    print("\nALL 9 PHASE 3 & 4 TESTS PASSED ON LOCAL HARDHAT BLOCKCHAIN.")
