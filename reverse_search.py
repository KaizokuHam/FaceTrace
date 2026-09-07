import os
import sys
import json
from urllib.parse import urlparse
from dotenv import load_dotenv
import serpapi
from PIL import Image

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Supported social media platforms
SOCIAL_DOMAINS = [
    "instagram.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "linkedin.com",
    "tiktok.com",
    "threads.net",
    "reddit.com",
]

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_FILE_SIZE_BYTES = 500 * 1024  # 500 KB limit for SerpApi image uploads


def validate_image_file(image_path):
    """Validate image exists, supported format, readable, and <= 500 KB."""
    if not os.path.exists(image_path):
        base, current_ext = os.path.splitext(image_path)
        if current_ext.lower() == ".jpg" and os.path.exists(base + ".jpeg"):
            image_path = base + ".jpeg"
        elif current_ext.lower() == ".jpeg" and os.path.exists(base + ".jpg"):
            image_path = base + ".jpg"

    if not os.path.exists(image_path):
        print(f"Error: Input image file not found at '{image_path}'.")
        print("TEST IMAGE REQUIRED")
        print("PHASE 0 TEST IMAGE REQUIRED")
        sys.exit(2)

    ext = os.path.splitext(image_path)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        print(f"Error: Unsupported image extension '{ext}'. Must be one of: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
        print("PHASE 0 API FAILURE")
        sys.exit(1)

    file_size = os.path.getsize(image_path)
    if file_size > MAX_FILE_SIZE_BYTES:
        print(f"Error: Image size ({file_size} bytes) exceeds 500 KB limit ({MAX_FILE_SIZE_BYTES} bytes).")
        print("PHASE 0 API FAILURE")
        sys.exit(1)

    try:
        with Image.open(image_path) as img:
            img.verify()
            fmt = img.format.upper() if img.format else ""
            if fmt not in ALLOWED_PIL_FORMATS:
                print(f"Error: Image format '{fmt}' is not supported. Must be JPEG, PNG, or WEBP.")
                print("PHASE 0 API FAILURE")
                sys.exit(1)
    except Exception as e:
        print(f"Error: Cannot read or verify image file '{image_path}': {e}")
        print("PHASE 0 API FAILURE")
        sys.exit(1)

    return image_path


def match_social_domain(link):
    """Dynamically match URL against supported social platforms."""
    if not link or not isinstance(link, str):
        return None
    try:
        netloc = urlparse(link).netloc.lower()
        if not netloc:
            return None
        for domain in SOCIAL_DOMAINS:
            if netloc == domain or netloc.endswith("." + domain):
                return domain
    except Exception:
        pass
    return None


def extract_social_candidates(items):
    """Extract and structure candidate social media URLs from match items."""
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        link = item.get("link") or item.get("source_link") or item.get("url") or ""
        matched_domain = match_social_domain(link)
        if matched_domain:
            candidates.append({
                "platform": matched_domain,
                "title": item.get("title", ""),
                "url": link,
                "position": item.get("position"),
                "source": item.get("source", ""),
            })
    return candidates


def get_match_items(data, primary_key):
    """Retrieve result list from SerpApi response structure."""
    if not isinstance(data, dict):
        return []

    # Direct key lookup
    items = data.get(primary_key)
    if isinstance(items, list):
        return items

    # Fallback to visual_matches if primary is exact_matches
    if primary_key == "exact_matches":
        vm = data.get("visual_matches")
        if isinstance(vm, list):
            exact_subset = [m for m in vm if isinstance(m, dict) and m.get("exact_matches") is True]
            return exact_subset if exact_subset else vm

    return []


def print_candidate(cand):
    """Print structured candidate info."""
    print("Discovered Social Candidate:")
    print(f"  Platform: {cand['platform']}")
    print(f"  Title: {cand['title'] if cand['title'] else 'N/A'}")
    print(f"  URL: {cand['url']}")
    print(f"  Position: {cand['position'] if cand['position'] is not None else 'N/A'}")


def reverse_image_search(image_path="examples/demo.jpg", standalone=True):
    # 1. Load environment variables
    load_dotenv()
    api_key = os.getenv("SERPAPI_API_KEY")

    # 2. Check API key presence without printing it
    if not api_key or not api_key.strip():
        print("Error: SERPAPI_API_KEY not found in .env file.")
        if standalone:
            print("PHASE 0 API FAILURE")
            sys.exit(1)
        raise RuntimeError("SERPAPI_API_KEY not found in .env file.")

    # 3. Validate image file
    image_path = validate_image_file(image_path)

    # 4. Initialize SerpApi client
    client = serpapi.Client(api_key=api_key)

    # 5. Upload local image to SerpApi
    print(f"Uploading local image '{image_path}' to SerpApi Image API...")
    try:
        upload_resp = client.upload_image(image_path)
    except Exception as e:
        err_msg = str(e).replace(api_key, "[REDACTED]")
        print(f"Error during image upload: {err_msg}")
        if standalone:
            print("PHASE 0 API FAILURE")
            sys.exit(1)
        raise RuntimeError(f"Error during image upload: {err_msg}")

    image_id = upload_resp.get("image_id") if isinstance(upload_resp, dict) else None
    if not image_id:
        error_info = upload_resp.get("error", "No image_id in response") if isinstance(upload_resp, dict) else str(upload_resp)
        print(f"Error: Upload failed. Details: {error_info}")
        if standalone:
            print("PHASE 0 API FAILURE")
            sys.exit(1)
        raise RuntimeError(f"Upload failed: {error_info}")

    print("Image upload succeeded.")
    print(f"image_id returned: {image_id}")

    os.makedirs("output", exist_ok=True)

    # 6. Live Google Lens search: exact_matches
    print("Executing live Google Lens search (type=exact_matches)...")
    exact_params = {
        "engine": "google_lens",
        "image_id": image_id,
        "type": "exact_matches",
        "no_cache": True,
    }

    try:
        exact_search = client.search(exact_params)
        exact_data = exact_search.as_dict() if hasattr(exact_search, "as_dict") else dict(exact_search)
    except Exception as e:
        err_msg = str(e).replace(api_key, "[REDACTED]")
        print(f"Error during Google Lens exact_matches search: {err_msg}")
        if standalone:
            print("PHASE 0 API FAILURE")
            sys.exit(1)
        raise RuntimeError(f"Error during exact_matches search: {err_msg}")

    if isinstance(exact_data, dict) and "error" in exact_data:
        print(f"Error returned by SerpApi: {exact_data['error']}")
        if standalone:
            print("PHASE 0 API FAILURE")
            sys.exit(1)
        raise RuntimeError(f"SerpApi error: {exact_data['error']}")

    # Save exact matches raw response
    exact_output_file = os.path.join("output", "phase0_exact_matches.json")
    with open(exact_output_file, "w", encoding="utf-8") as f:
        json.dump(exact_data, f, indent=2)
    print(f"Raw exact matches response saved to: {exact_output_file}")

    exact_items = get_match_items(exact_data, "exact_matches")
    print(f"Number of exact matches: {len(exact_items)}")

    # 7. Dynamically filter exact matches for social domains
    exact_social = extract_social_candidates(exact_items)
    for cand in exact_social:
        print_candidate(cand)

    # 8. Visual matches fallback if no social media candidate found
    visual_social = []
    visual_items = []
    visual_output_file = None
    if not exact_social:
        print("No social-media result found in exact matches. Running visual matches fallback...")
        visual_params = {
            "engine": "google_lens",
            "image_id": image_id,
            "type": "visual_matches",
            "no_cache": True,
        }

        try:
            visual_search = client.search(visual_params)
            visual_data = visual_search.as_dict() if hasattr(visual_search, "as_dict") else dict(visual_search)
        except Exception as e:
            err_msg = str(e).replace(api_key, "[REDACTED]")
            print(f"Error during Google Lens visual_matches search: {err_msg}")
            if standalone:
                print("PHASE 0 API FAILURE")
                sys.exit(1)
            raise RuntimeError(f"Error during visual_matches search: {err_msg}")

        if isinstance(visual_data, dict) and "error" in visual_data:
            print(f"Error returned by SerpApi: {visual_data['error']}")
            if standalone:
                print("PHASE 0 API FAILURE")
                sys.exit(1)
            raise RuntimeError(f"SerpApi error: {visual_data['error']}")

        visual_output_file = os.path.join("output", "phase0_visual_matches.json")
        with open(visual_output_file, "w", encoding="utf-8") as f:
            json.dump(visual_data, f, indent=2)
        print(f"Raw visual matches response saved to: {visual_output_file}")

        visual_items = get_match_items(visual_data, "visual_matches")
        print(f"Number of visual matches: {len(visual_items)}")

        visual_social = extract_social_candidates(visual_items)
        for cand in visual_social:
            print_candidate(cand)

    # 9. Evaluate outcome
    all_discovered = exact_social if exact_social else visual_social
    result_payload = {
        "upload_succeeded": True,
        "image_id": image_id,
        "exact_matches_count": len(exact_items),
        "visual_matches_count": len(visual_items) if not exact_social else 0,
        "exact_matches_file": exact_output_file,
        "visual_matches_file": visual_output_file,
        "social_candidates": all_discovered,
        "exact_social": exact_social,
        "visual_social": visual_social,
        "status": "PHASE 0 PASS" if all_discovered else "PHASE 0 NO SOCIAL MATCH"
    }

    if standalone:
        if all_discovered:
            print("\nPHASE 0 PASS")
            sys.exit(0)
        else:
            print("\nPHASE 0 NO SOCIAL MATCH")
            sys.exit(0)

    return result_payload


if __name__ == "__main__":
    target_path = sys.argv[1] if len(sys.argv) > 1 else "examples/demo.jpg"
    reverse_image_search(target_path, standalone=True)
