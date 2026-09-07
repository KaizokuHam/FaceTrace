import os
import sys
import hashlib
import numpy as np
from face_processor import (
    compute_file_sha256,
    serialize_embedding,
    compute_embedding_sha256,
    process_face,
)
from reverse_search import match_social_domain, extract_social_candidates


def test_image_sha256_deterministic():
    """Verify SHA-256 computation on image bytes is 100% deterministic."""
    image_path = "examples/demo.jpg"
    assert os.path.exists(image_path), "examples/demo.jpg must exist for this test"

    h1 = compute_file_sha256(image_path)
    h2 = compute_file_sha256(image_path)
    assert h1 == h2, "SHA-256 hashes must match across consecutive reads"
    assert len(h1) == 64, "SHA-256 hex digest must be 64 characters long"


def test_embedding_serialization_and_hash_deterministic():
    """Verify embedding serialization to float32 and SHA-256 hashing is 100% deterministic."""
    # Fixed synthetic embedding vector (1434 floats)
    rng = np.random.default_rng(42)
    sample_embedding = rng.standard_normal(1434, dtype=np.float32)

    bytes1, hash1 = compute_embedding_sha256(sample_embedding)
    bytes2, hash2 = compute_embedding_sha256(sample_embedding)

    assert bytes1 == bytes2, "Serialized bytes must be identical"
    assert hash1 == hash2, "Embedding SHA-256 hashes must be identical"
    assert len(bytes1) == 1434 * 4, f"Expected {1434 * 4} bytes for float32 vector, got {len(bytes1)}"
    assert len(hash1) == 64, "Embedding SHA-256 hex digest must be 64 characters"


def test_social_domain_filtering():
    """Verify dynamic matching against all supported social media domains and rejection of non-social domains."""
    valid_test_cases = [
        ("https://www.instagram.com/p/ABC123xyz/", "instagram.com"),
        ("https://instagram.com/profile/", "instagram.com"),
        ("https://twitter.com/user/status/12345", "twitter.com"),
        ("https://x.com/user/status/67890", "x.com"),
        ("https://www.facebook.com/groups/post/111", "facebook.com"),
        ("https://linkedin.com/posts/activity-12345", "linkedin.com"),
        ("https://be.linkedin.com/in/someone", "linkedin.com"),
        ("https://www.tiktok.com/@user/video/999", "tiktok.com"),
        ("https://threads.net/@user/post/333", "threads.net"),
        ("https://www.reddit.com/r/technology/comments/1", "reddit.com"),
    ]

    for url, expected_domain in valid_test_cases:
        assert match_social_domain(url) == expected_domain, f"Expected {expected_domain} for {url}"

    invalid_test_cases = [
        "https://google.com/search?q=test",
        "https://not-instagram.com/post/1",
        "https://fake-x.com/profile",
        "https://github.com/opencv/opencv",
        "",
        None,
    ]

    for url in invalid_test_cases:
        assert match_social_domain(url) is None, f"Expected None for {url}"


def test_social_candidates_extraction():
    """Verify extraction of candidate social links from raw match lists."""
    items = [
        {"link": "https://www.instagram.com/p/test", "title": "IG Post", "position": 1},
        {"link": "https://techcrunch.com/article", "title": "News", "position": 2},
        {"link": "https://x.com/tech/status/123", "title": "X Post", "position": 3},
    ]
    candidates = extract_social_candidates(items)
    assert len(candidates) == 2
    assert candidates[0]["platform"] == "instagram.com"
    assert candidates[1]["platform"] == "x.com"


def test_no_face_detection_on_blank_image():
    """Verify that process_face correctly detects 0 faces on an image without human faces."""
    import cv2
    import tempfile

    # Create a 200x200 blank image
    blank = np.zeros((200, 200, 3), dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        temp_path = tf.name
    try:
        cv2.imwrite(temp_path, blank)
        result = process_face(temp_path)
        assert result["success"] is False
        assert result["error_code"] == "NO_FACES"
        assert result["face_count"] == 0
        assert result["embedding"] is None
        assert result["embedding_sha256"] is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_single_face_detection_on_demo_image():
    """Verify that process_face detects exactly 1 face on the live demo image."""
    image_path = "examples/demo.jpg"
    assert os.path.exists(image_path), "examples/demo.jpg must exist for this test"

    result = process_face(image_path)
    assert result["success"] is True
    assert result["face_count"] == 1
    assert result["embedding"] is not None
    assert len(result["embedding"]) == 1434
    assert len(result["embedding_sha256"]) == 64


def test_multi_face_failure_handling():
    """Verify that multiple faces triggers clear failure without choosing silently."""
    from face_processor import process_face
    from unittest.mock import patch

    # Mock detect_faces to simulate 2 faces detected
    with patch("face_processor.detect_faces", return_value=["face_1", "face_2"]):
        result = process_face("examples/demo.jpg")
        assert result["success"] is False
        assert result["error_code"] == "MULTIPLE_FACES"
        assert result["face_count"] == 2
        assert "Multiple faces detected (2 faces)" in result["message"]
        assert result["embedding"] is None


if __name__ == "__main__":
    print("Running Phase 1 test suite...")
    test_image_sha256_deterministic()
    print("  [PASS] test_image_sha256_deterministic")
    test_embedding_serialization_and_hash_deterministic()
    print("  [PASS] test_embedding_serialization_and_hash_deterministic")
    test_social_domain_filtering()
    print("  [PASS] test_social_domain_filtering")
    test_social_candidates_extraction()
    print("  [PASS] test_social_candidates_extraction")
    test_no_face_detection_on_blank_image()
    print("  [PASS] test_no_face_detection_on_blank_image")
    test_single_face_detection_on_demo_image()
    print("  [PASS] test_single_face_detection_on_demo_image")
    test_multi_face_failure_handling()
    print("  [PASS] test_multi_face_failure_handling")
    print("\nALL PHASE 1 TESTS PASSED.")
