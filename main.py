import os
import sys
from face_processor import process_face
from reverse_search import reverse_image_search, print_candidate
from evidence_manager import (
    select_best_social_candidate,
    create_evidence_manifest,
    hash_evidence,
    save_evidence,
    compute_search_response_sha256,
)

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run_pipeline(image_path: str = "examples/demo.jpg"):
    print("==================================================")
    print("        HACKER HOUSE GOA 2026 - MAIN PIPELINE")
    print("==================================================")

    # STEP 1: Load and Hash Image
    print("\n[1/4] Loading image...")
    if not os.path.exists(image_path):
        print(f"      Error: Image file not found at '{image_path}'")
        print("\nPHASE 1 FACE INPUT FAILURE")
        sys.exit(1)

    print(f"      Target image: {image_path}")

    # STEP 2: Detect Face & Generate Numeric Embedding
    print("\n[2/4] Detecting face...")
    try:
        face_result = process_face(image_path)
    except Exception as e:
        print(f"      Error processing face: {e}")
        print("\nPHASE 1 DEPENDENCY FAILURE")
        sys.exit(1)

    source_image_sha256 = face_result["image_sha256"]
    print(f"      Source Image SHA-256: {source_image_sha256}")
    face_count = face_result["face_count"]

    if face_count == 0:
        print(f"      Faces detected: 0")
        print("      Error: No detectable face found in the input image.")
        print("      DEMO IMAGE NOT SUITABLE FOR FACE PIPELINE")
        print("\nPHASE 1 FACE INPUT FAILURE")
        sys.exit(0)

    if face_count > 1:
        print(f"      Faces detected: {face_count}")
        print(f"      Error: Multiple faces detected ({face_count}). Exactly one face is required.")
        print("      DEMO IMAGE NOT SUITABLE FOR FACE PIPELINE")
        print("\nPHASE 1 FACE INPUT FAILURE")
        sys.exit(0)

    # Exactly one face detected
    print("      Exactly one face detected.")
    face_encoding_sha256 = face_result["embedding_sha256"]
    print(f"      Embedding generated ({face_result['embedding_dim']}-D normalized numerical vector)")
    print(f"      Embedding SHA-256: {face_encoding_sha256}")

    # STEP 3: Live Reverse-Image Search (Phase 0 integration)
    print("\n[3/4] Live reverse-image search (SerpApi Google Lens)...")
    try:
        search_result = reverse_image_search(image_path, standalone=False)
    except Exception as e:
        print(f"      Reverse search error: {e}")
        print("\nPHASE 1 DEPENDENCY FAILURE")
        sys.exit(1)

    print(f"      Upload succeeded: {search_result['upload_succeeded']}")
    print(f"      Provider image_id: {search_result['image_id']}")
    print(f"      Exact matches count: {search_result['exact_matches_count']}")
    if search_result.get("visual_matches_count", 0) > 0:
        print(f"      Visual matches count: {search_result['visual_matches_count']}")
    print(f"      Discovered social candidates: {len(search_result['social_candidates'])}")

    # STEP 4: Matching Candidates Output & Canonical Evidence Creation
    print("\n[4/4] Matching candidates:")
    candidates = search_result["social_candidates"]
    if not candidates:
        print("      No social media matches discovered.")
        print("\nPHASE 1 NO SOCIAL MATCH")
        sys.exit(0)

    # Print first 5 candidate summaries
    print(f"      Discovered {len(candidates)} social media candidates. Top candidates:")
    for cand in candidates[:5]:
        print_candidate(cand)

    # Phase 3: Deterministic Candidate Selection & Evidence Generation
    selected_candidate = select_best_social_candidate(candidates)
    if not selected_candidate:
        print("      Error: Could not select a candidate from search results.")
        print("\nPHASE 1 NO SOCIAL MATCH")
        sys.exit(0)

    if search_result["exact_social"]:
        search_type = "exact_matches"
        search_response_path = search_result["exact_matches_file"]
    else:
        search_type = "visual_matches"
        search_response_path = search_result["visual_matches_file"]

    evidence_manifest = create_evidence_manifest(
        source_image_sha256=source_image_sha256,
        face_encoding_sha256=face_encoding_sha256,
        matched_candidate=selected_candidate,
        search_response_sha256=compute_search_response_sha256(search_response_path),
        search_provider="google_lens_serpapi",
        search_type=search_type,
    )

    evidence_path = save_evidence(evidence_manifest, "output/evidence.json")
    evidence_sha256 = hash_evidence(evidence_manifest)

    print("\n==================================================")
    print("           CANONICAL EVIDENCE GENERATED")
    print("==================================================")
    print(f"  Selected Platform:       {selected_candidate['platform']}")
    print(f"  Selected URL:            {selected_candidate['url']}")
    print(f"  Provider Position:       {selected_candidate['provider_position']}")
    print(f"  Evidence File Path:      {evidence_path}")
    print(f"  Canonical SHA-256:       {evidence_sha256}")
    print("==================================================")

    print("\nPHASE 1 PASS")
    return evidence_manifest


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "examples/demo.jpg"
    run_pipeline(target)
