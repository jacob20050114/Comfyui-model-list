#!/usr/bin/env python3
"""Validate model-list.json: syntax, schema, duplicates, and URL reachability."""

import json
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

MODEL_LIST_PATH = "model-list.json"

REQUIRED_FIELDS = ["name", "type", "base", "save_path", "description", "reference", "filename", "url"]


def validate_json_syntax(path):
    """Check that the file is valid JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print("[PASS] JSON syntax is valid")
        return data
    except json.JSONDecodeError as e:
        print(f"[FAIL] JSON syntax error: {e}")
        return None


def validate_schema(models):
    """Check that every model entry has all required fields."""
    errors = []
    for i, model in enumerate(models):
        for field in REQUIRED_FIELDS:
            if field not in model:
                errors.append(f"  Model #{i} ({model.get('name', 'unknown')}): missing field '{field}'")
    if errors:
        print("[FAIL] Schema validation failed:")
        for e in errors:
            print(e)
        return False
    print(f"[PASS] All {len(models)} models have required fields")
    return True


def validate_duplicates(models):
    """Check for duplicate filenames and URLs."""
    ok = True

    # Check duplicate filenames (skip <huggingface> placeholder)
    filenames = {}
    for i, model in enumerate(models):
        fn = model.get("filename", "")
        if fn and fn != "<huggingface>":
            if fn in filenames:
                print(f"[FAIL] Duplicate filename '{fn}' in model #{filenames[fn]} and #{i}")
                ok = False
            else:
                filenames[fn] = i

    # Check duplicate URLs
    urls = {}
    for i, model in enumerate(models):
        url = model.get("url", "")
        if url:
            if url in urls:
                print(f"[FAIL] Duplicate URL '{url}' in model #{urls[url]} and #{i}")
                ok = False
            else:
                urls[url] = i

    if ok:
        print("[PASS] No duplicate filenames or URLs")
    return ok


def check_url(name, url):
    """Send a HEAD request to verify URL is reachable. Returns (name, url, ok, detail)."""
    # Skip non-HTTP URLs (e.g. huggingface repo IDs)
    if not url.startswith("http://") and not url.startswith("https://"):
        return (name, url, True, "skipped (not an HTTP URL)")

    req = urllib.request.Request(url, method="HEAD")
    req.add_header("User-Agent", "comfyui-model-list-ci/1.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return (name, url, True, f"HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        # Some servers don't support HEAD, try GET with range
        if e.code == 405:
            try:
                req2 = urllib.request.Request(url, method="GET")
                req2.add_header("User-Agent", "comfyui-model-list-ci/1.0")
                req2.add_header("Range", "bytes=0-0")
                with urllib.request.urlopen(req2, timeout=30) as resp:
                    return (name, url, True, f"HTTP {resp.status} (GET fallback)")
            except Exception as e2:
                return (name, url, False, f"GET fallback failed: {e2}")
        return (name, url, False, f"HTTP {e.code}")
    except Exception as e:
        return (name, url, False, str(e))


def validate_urls(models):
    """Check that all URLs are reachable."""
    tasks = [(m.get("name", "unknown"), m.get("url", "")) for m in models if m.get("url")]
    ok = True

    print(f"[INFO] Checking {len(tasks)} URLs...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(check_url, name, url): (name, url) for name, url in tasks}
        for future in as_completed(futures):
            name, url, reachable, detail = future.result()
            if reachable:
                print(f"  [OK] {name}: {detail}")
            else:
                print(f"  [FAIL] {name}: {detail}")
                print(f"         URL: {url}")
                ok = False

    if ok:
        print("[PASS] All URLs are reachable")
    else:
        print("[FAIL] Some URLs are not reachable")
    return ok


def main():
    print("=" * 60)
    print("Validating model-list.json")
    print("=" * 60)

    data = validate_json_syntax(MODEL_LIST_PATH)
    if data is None:
        sys.exit(1)

    if "models" not in data or not isinstance(data["models"], list):
        print("[FAIL] JSON must have a top-level 'models' array")
        sys.exit(1)

    models = data["models"]
    results = []

    print()
    results.append(validate_schema(models))

    print()
    results.append(validate_duplicates(models))

    print()
    results.append(validate_urls(models))

    print()
    print("=" * 60)
    if all(results):
        print("All checks passed!")
    else:
        print("Some checks failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
