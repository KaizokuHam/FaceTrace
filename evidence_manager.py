import os
import sys
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Any

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

MERKLE_FIELDS = [
    "face_encoding_sha256",
    "matched_platform",
    "matched_post_sha256",
    "matched_title",
    "matched_url",
    "provider_position",
    "search_provider",
    "search_response_sha256",
    "search_type",
    "source_image_sha256",
]


def compute_search_response_sha256(response_file_path: str = "output/phase0_exact_matches.json") -> str:
    """
    Compute deterministic SHA-256 hash of the exact raw search response bytes.
    Binds the evidence cryptographically to the live search provider output.
    """
    if not os.path.exists(response_file_path):
        raise FileNotFoundError(f"Raw search response not found at: {response_file_path}")
    with open(response_file_path, "rb") as f:
        data = f.read()
    return hashlib.sha256(data).hexdigest()


def compute_matched_post_fingerprint(candidate: dict) -> str:
    """
    Create a deterministic fingerprint specifically representing the selected social post.
    Canonicalizes the post object with sorted compact JSON before hashing.
    """
    pos = candidate.get("provider_position")
    if pos is None:
        pos = candidate.get("position")
    post_obj = {
        "platform": candidate.get("platform", ""),
        "provider_position": pos,
        "title": candidate.get("title", ""),
        "url": candidate.get("url", ""),
    }
    canonical_post_bytes = json.dumps(
        post_obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical_post_bytes).hexdigest()


def is_content_post_url(url: str, platform: str) -> bool:
    """
    Determine if a candidate URL represents an actual content post/status/video
    rather than a profile, search, trending, or generic landing page.
    """
    if not url or not isinstance(url, str):
        return False
    u = url.lower()

    if platform in ("x.com", "twitter.com"):
        return "/status/" in u and "/trending" not in u and "/search" not in u

    if platform == "linkedin.com":
        return ("/posts/" in u or "/pulse/" in u) and "/in/" not in u

    if platform == "facebook.com":
        return "/posts/" in u or "/photos/" in u or "/permalink/" in u

    if platform == "reddit.com":
        return "/comments/" in u

    if platform == "tiktok.com":
        return "/video/" in u

    return False


def score_candidate(candidate: dict) -> tuple[float, dict]:
    """
    Compute a deterministic selection score and detailed breakdown for a candidate.
    Signals:
    - Specific post URL bonus (+50)
    - Platform priority weight (x.com/twitter=40, linkedin=30, facebook=25, reddit=20, tiktok=15)
    - Provider position score (earlier positions favored)
    - Profile/trending/search penalty (-50)
    """
    url = candidate.get("url", "")
    platform = candidate.get("platform", "")
    pos = candidate.get("position")
    pos_val = pos if (pos is not None and isinstance(pos, int)) else 500

    is_post = is_content_post_url(url, platform)
    post_bonus = 50.0 if is_post else 0.0

    platform_weights = {
        "x.com": 40.0,
        "twitter.com": 40.0,
        "linkedin.com": 30.0,
        "facebook.com": 25.0,
        "reddit.com": 20.0,
        "tiktok.com": 15.0,
    }
    platform_weight = platform_weights.get(platform, 0.0)

    # Position score: linear decay from 50 down to 0
    position_score = max(0.0, 50.0 - (pos_val * 0.2))

    # Penalties for non-content pages
    penalty = 0.0
    u = url.lower()
    if "/i/trending" in u or "/search" in u or "/hashtag/" in u:
        penalty += 50.0
    if not is_post and ("/in/" in u or "/user/" in u or "/profile" in u):
        penalty += 30.0

    total_score = round(post_bonus + platform_weight + position_score - penalty, 2)
    components = {
        "specific_post_bonus": post_bonus,
        "platform_priority_weight": platform_weight,
        "position_score": round(position_score, 2),
        "penalty": penalty,
    }
    return total_score, components


def rank_and_score_candidates(
    candidates: list[dict],
    save_path: str = "output/ranked_candidates.json",
) -> list[dict]:
    """
    Score all candidates, sort descending by score (tie-breaking on URL),
    and persist the candidate ranking receipt to disk.
    """
    scored = []
    for c in candidates:
        score, comps = score_candidate(c)
        entry = {
            "platform": c.get("platform", ""),
            "url": c.get("url", ""),
            "title": c.get("title", ""),
            "provider_position": c.get("position"),
            "is_specific_post": is_content_post_url(c.get("url", ""), c.get("platform", "")),
            "selection_score": score,
            "selection_components": comps,
        }
        scored.append(entry)

    # Sort descending by selection score, then ascending by provider position, then ascending by url
    ranked = sorted(
        scored,
        key=lambda x: (-x["selection_score"], x["provider_position"] if x["provider_position"] is not None else 9999, x["url"])
    )

    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(ranked, f, indent=2, ensure_ascii=False)

    return ranked


def select_best_social_candidate(candidates: list[dict]) -> Optional[dict]:
    """
    Deterministically select the highest-scoring candidate from live provider results.
    """
    ranked = rank_and_score_candidates(candidates)
    return ranked[0] if ranked else None


def create_evidence_manifest(
    source_image_sha256: str,
    face_encoding_sha256: str,
    matched_candidate: dict,
    search_response_sha256: Optional[str] = None,
    search_provider: str = "google_lens_serpapi",
    search_type: str = "exact_matches",
    created_at: Optional[str] = None,
) -> dict:
    """
    Construct the cryptographic evidence manifest with search provenance and post fingerprint.
    """
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()

    if search_response_sha256 is None:
        try:
            search_response_sha256 = compute_search_response_sha256()
        except Exception:
            search_response_sha256 = "unavailable"

    matched_post_sha256 = compute_matched_post_fingerprint(matched_candidate)

    return {
        "version": "1.0",
        "source_image_sha256": source_image_sha256,
        "face_encoding_sha256": face_encoding_sha256,
        "search_provider": search_provider,
        "search_type": search_type,
        "search_response_sha256": search_response_sha256,
        "matched_platform": matched_candidate.get("platform", ""),
        "matched_url": matched_candidate.get("url", ""),
        "matched_title": matched_candidate.get("title", ""),
        "provider_position": (
            matched_candidate.get("provider_position")
            if matched_candidate.get("provider_position") is not None
            else matched_candidate.get("position")
        ),
        "matched_post_sha256": matched_post_sha256,
        "created_at": created_at,
    }


def canonicalize_evidence(evidence: dict) -> bytes:
    """
    Deterministically serialize evidence manifest into canonical UTF-8 bytes.
    Uses sorted keys and compact delimiters without whitespace.
    """
    canonical_json_str = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return canonical_json_str.encode("utf-8")


def hash_evidence(evidence: dict) -> str:
    """
    Compute SHA-256 digest of the canonicalized evidence manifest.
    """
    canonical_bytes = canonicalize_evidence(evidence)
    return hashlib.sha256(canonical_bytes).hexdigest()


# ==================================================
# MERKLE TREE IMPLEMENTATION
# ==================================================

def sha256_combine(left_hex: str, right_hex: str) -> str:
    """Hash concatenation of two 32-byte binary nodes."""
    return hashlib.sha256(bytes.fromhex(left_hex) + bytes.fromhex(right_hex)).hexdigest()


def compute_merkle_leaf(field_name: str, value: Any) -> tuple[str, str]:
    """
    Compute deterministic Merkle leaf hash:
    leaf = SHA256(UTF8(field_name + ":" + canonical_string_value))
    """
    val_str = str(value) if value is not None else ""
    raw_str = f"{field_name}:{val_str}"
    leaf_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    return raw_str, leaf_hash


def build_merkle_evidence(
    evidence: dict,
    save_path: str = "output/merkle_evidence.json",
) -> dict:
    """
    Construct a deterministic Merkle tree over the evidence manifest fields.
    Sorts leaves lexicographically by field name.
    Computes inclusion proofs for all leaves.
    Persists structured tree and proofs to output/merkle_evidence.json.
    """
    # 1. Generate sorted leaves
    sorted_fields = sorted(MERKLE_FIELDS)
    leaves_info = {}
    leaf_hashes = []

    for field in sorted_fields:
        val = evidence.get(field, "")
        raw_repr, h = compute_merkle_leaf(field, val)
        leaves_info[field] = {
            "value": val,
            "raw_leaf_string": raw_repr,
            "leaf_hash": h,
        }
        leaf_hashes.append(h)

    # 2. Build tree levels
    levels = [list(leaf_hashes)]
    curr = list(leaf_hashes)

    while len(curr) > 1:
        if len(curr) % 2 != 0:
            curr.append(curr[-1])  # Duplicate final node if odd
        nxt = []
        for i in range(0, len(curr), 2):
            nxt.append(sha256_combine(curr[i], curr[i + 1]))
        levels.append(nxt)
        curr = nxt

    merkle_root = levels[-1][0]

    # 3. Generate inclusion proofs for every field
    proofs = {}
    for idx, field in enumerate(sorted_fields):
        field_proof = []
        cur_idx = idx
        for l_idx in range(len(levels) - 1):
            lvl = list(levels[l_idx])
            if len(lvl) % 2 != 0:
                lvl.append(lvl[-1])
            sibling_idx = cur_idx + 1 if cur_idx % 2 == 0 else cur_idx - 1
            pos = "right" if cur_idx % 2 == 0 else "left"
            field_proof.append({
                "position": pos,
                "hash": lvl[sibling_idx],
            })
            cur_idx = cur_idx // 2
        proofs[field] = field_proof

    merkle_manifest = {
        "merkle_root": merkle_root,
        "leaf_count": len(sorted_fields),
        "leaves": leaves_info,
        "proofs": proofs,
    }

    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(merkle_manifest, f, indent=2, ensure_ascii=False)

    return merkle_manifest


def verify_merkle_proof(
    leaf_hash: str,
    proof: list[dict],
    expected_root: str,
) -> bool:
    """
    Verify a cryptographic Merkle inclusion proof against the expected root.
    """
    curr = leaf_hash
    for step in proof:
        sibling = step["hash"]
        if step["position"] == "right":
            curr = sha256_combine(curr, sibling)
        else:
            curr = sha256_combine(sibling, curr)
    return curr.lower() == expected_root.lower()


def save_evidence(evidence: dict, file_path: str = "output/evidence.json") -> str:
    """Persist the evidence manifest locally to disk."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)
    return file_path


def load_evidence(file_path: str = "output/evidence.json") -> dict:
    """Load persisted evidence manifest from disk."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Evidence file not found at: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
