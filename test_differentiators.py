import os
import sys
import json
import tempfile
import hashlib
from web3 import Web3

from evidence_manager import (
    compute_search_response_sha256,
    compute_matched_post_fingerprint,
    score_candidate,
    rank_and_score_candidates,
    build_merkle_evidence,
    verify_merkle_proof,
    canonicalize_evidence,
    hash_evidence,
    create_evidence_manifest,
    save_evidence,
    load_evidence,
    MERKLE_FIELDS,
)
from blockchain_client import (
    get_web3_client,
    get_contract_instance,
    attest_commitment,
    verify_evidence_on_chain,
    run_multi_tamper_test,
    hash_to_bytes32,
)

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def test_search_response_hashing():
    """1. Test that search-response hashing is deterministic and matches raw bytes."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tf.write(b'{"sample": "search_results_data_12345"}')
        path = tf.name
    try:
        h1 = compute_search_response_sha256(path)
        h2 = compute_search_response_sha256(path)
        expected = hashlib.sha256(b'{"sample": "search_results_data_12345"}').hexdigest()
        assert h1 == h2 == expected
        assert len(h1) == 64
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_matched_post_fingerprint_determinism():
    """2. Test that matched-post fingerprint is strictly deterministic regardless of input key order."""
    p1 = {
        "platform": "x.com",
        "url": "https://x.com/user/status/123",
        "title": "Sample Title",
        "position": 5,
    }
    p2 = {
        "title": "Sample Title",
        "position": 5,
        "platform": "x.com",
        "url": "https://x.com/user/status/123",
    }
    fp1 = compute_matched_post_fingerprint(p1)
    fp2 = compute_matched_post_fingerprint(p2)
    assert fp1 == fp2, "Post fingerprints must match regardless of dictionary ordering"
    assert len(fp1) == 64


def test_candidate_ranking_determinism():
    """3. Test candidate ranking determinism and scoring priority."""
    candidates = [
        {"platform": "facebook.com", "url": "https://facebook.com/user/profile", "position": 2},
        {"platform": "x.com", "url": "https://x.com/i/trending/123", "position": 1},
        {"platform": "x.com", "url": "https://x.com/post/status/456", "position": 10},
        {"platform": "linkedin.com", "url": "https://linkedin.com/posts/item-1", "position": 5},
    ]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        ranked_path = tf.name
    try:
        ranked = rank_and_score_candidates(candidates, save_path=ranked_path)
        # x.com post should outrank trending/profile pages despite lower provider position
        assert ranked[0]["url"] == "https://x.com/post/status/456"
        assert ranked[0]["is_specific_post"] is True
        assert os.path.exists(ranked_path)
    finally:
        if os.path.exists(ranked_path):
            os.remove(ranked_path)


def test_merkle_root_determinism():
    """4. Test that Merkle root generation is 100% deterministic for identical evidence."""
    ev = {
        "version": "1.0",
        "source_image_sha256": "1" * 64,
        "face_encoding_sha256": "2" * 64,
        "search_response_sha256": "3" * 64,
        "matched_post_sha256": "4" * 64,
        "matched_platform": "x.com",
        "matched_url": "https://x.com/status/999",
        "matched_title": "Title",
        "provider_position": 1,
        "search_provider": "google_lens_serpapi",
        "search_type": "exact_matches",
    }
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        p1 = tf.name
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf2:
        p2 = tf2.name
    try:
        m1 = build_merkle_evidence(ev, save_path=p1)
        m2 = build_merkle_evidence(ev, save_path=p2)
        assert m1["merkle_root"] == m2["merkle_root"]
        assert len(m1["merkle_root"]) == 64
        assert m1["leaf_count"] == 10
    finally:
        for p in (p1, p2):
            if os.path.exists(p):
                os.remove(p)


def test_merkle_inclusion_proof_success():
    """5. Test that generated Merkle inclusion proofs successfully verify against root."""
    ev = {
        "version": "1.0",
        "source_image_sha256": "a" * 64,
        "face_encoding_sha256": "b" * 64,
        "search_response_sha256": "c" * 64,
        "matched_post_sha256": "d" * 64,
        "matched_platform": "x.com",
        "matched_url": "https://x.com/status/100",
        "matched_title": "Verified Post",
        "provider_position": 47,
        "search_provider": "google_lens_serpapi",
        "search_type": "exact_matches",
    }
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        p = tf.name
    try:
        tree = build_merkle_evidence(ev, save_path=p)
        root = tree["merkle_root"]
        for field in MERKLE_FIELDS:
            leaf_h = tree["leaves"][field]["leaf_hash"]
            proof = tree["proofs"][field]
            assert verify_merkle_proof(leaf_h, proof, root) is True
    finally:
        if os.path.exists(p):
            os.remove(p)


def test_wrong_merkle_proof_failure():
    """6. Test that invalid leaf hashes or corrupted proofs fail verification."""
    ev = {
        "source_image_sha256": "a" * 64,
        "matched_url": "https://x.com/status/100",
    }
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        p = tf.name
    try:
        tree = build_merkle_evidence(ev, save_path=p)
        root = tree["merkle_root"]
        fake_leaf = "0" * 64
        proof = tree["proofs"]["matched_url"]
        assert verify_merkle_proof(fake_leaf, proof, root) is False
    finally:
        if os.path.exists(p):
            os.remove(p)


def test_four_tamper_cases():
    """7-10. Test that mutating URL, title, image hash, or search hash breaks on-chain verification."""
    evidence_path = "output/evidence.json"
    assert os.path.exists(evidence_path), "output/evidence.json must exist for tamper testing"

    tamper_results = run_multi_tamper_test(evidence_path)
    assert tamper_results["original_on_chain"] is True
    assert tamper_results["all_tamper_cases_rejected"] is True

    cases = tamper_results["cases"]
    # Case A: URL
    assert cases["case_a_url"]["roots_differ"] is True
    assert cases["case_a_url"]["on_chain_exists"] is False
    # Case B: Title
    assert cases["case_b_title"]["roots_differ"] is True
    assert cases["case_b_title"]["on_chain_exists"] is False
    # Case C: Image SHA256
    assert cases["case_c_image"]["roots_differ"] is True
    assert cases["case_c_image"]["on_chain_exists"] is False
    # Case D: Search Response SHA256
    assert cases["case_d_search"]["roots_differ"] is True
    assert cases["case_d_search"]["on_chain_exists"] is False

    assert tamper_results["disk_intact"] is True


def test_on_chain_merkle_root_lifecycle():
    """11-12. Test that freshly attested Merkle roots exist on-chain and unattested ones do not."""
    contract = get_contract_instance()
    unique_root = hashlib.sha256(f"unique_merkle_root_{os.urandom(16).hex()}".encode()).hexdigest()
    unattested_root = hashlib.sha256(b"unattested_merkle_root_never_committed").hexdigest()

    # Pre-attestation: exists is False
    assert contract.functions.exists(hash_to_bytes32(unique_root)).call() is False

    # Attest
    res = attest_commitment(unique_root)
    assert res["status"] == "SUCCESS"

    # Post-attestation: exists is True
    assert contract.functions.exists(hash_to_bytes32(unique_root)).call() is True
    # Unattested: exists is False
    assert contract.functions.exists(hash_to_bytes32(unattested_root)).call() is False


if __name__ == "__main__":
    print("Running Differentiator & Phase 6 Test Suite...")

    test_search_response_hashing()
    print("  [PASS] 1. Search-response hashing")

    test_matched_post_fingerprint_determinism()
    print("  [PASS] 2. Matched-post fingerprint determinism")

    test_candidate_ranking_determinism()
    print("  [PASS] 3. Candidate ranking determinism")

    test_merkle_root_determinism()
    print("  [PASS] 4. Merkle root determinism")

    test_merkle_inclusion_proof_success()
    print("  [PASS] 5. Merkle inclusion proof success (all leaves)")

    test_wrong_merkle_proof_failure()
    print("  [PASS] 6. Wrong Merkle proof failure")

    test_four_tamper_cases()
    print("  [PASS] 7-10. Multi-case tamper rejection (URL, title, image, search response)")

    test_on_chain_merkle_root_lifecycle()
    print("  [PASS] 11-12. On-chain Merkle root exists & unattested fails")

    print("\nALL PHASE 6 DIFFERENTIATOR TESTS PASSED.")
