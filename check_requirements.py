#!/usr/bin/env python3
"""Check every line of a requirements file against PyPI before running pip install.

Usage:
    python check_requirements.py [requirements.txt]
"""
import json
import re
import sys
import urllib.error
import urllib.request

PYPI = "https://pypi.org/pypi"

# name, optional [extras], optional operator + version. Accepts "==", "=", ">=", etc.
LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(===|==|=|>=|<=|~=|!=|>|<)?\s*([^\s;,#]+)?"
)

_cache = {}


def fetch_json(url):
    """Return parsed JSON, or None if PyPI answers 404. Other errors are raised."""
    if url in _cache:
        return _cache[url]
    req = urllib.request.Request(url, headers={"User-Agent": "requirements-checker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            data = None
        else:
            raise
    _cache[url] = data
    return data


def parse_line(raw):
    """Return (name, op, version) or None for lines that aren't package requirements."""
    line = raw.split("#", 1)[0].strip()
    if not line or line.startswith("-"):  # blank, comment, -r / -e / --index-url ...
        return None
    m = LINE_RE.match(line)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def main(path):
    checked = 0
    missing_packages = []
    missing_versions = []
    oldest = None  # (upload_time, name, version)

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    for raw in lines:
        parsed = parse_line(raw)
        if parsed is None:
            continue
        name, op, version = parsed
        checked += 1

        if fetch_json(f"{PYPI}/{name}/json") is None:
            missing_packages.append(name)
            continue

        # Only exact pins (== / = / ===) name one specific release to look up.
        if op not in ("==", "=", "===") or not version:
            continue

        release = fetch_json(f"{PYPI}/{name}/{version}/json")
        if release is None:
            missing_versions.append(f"{name}=={version}")
            continue

        files = release.get("urls") or []
        if not files:  # release exists but has no uploaded files
            continue
        upload_time = files[0].get("upload_time")
        if upload_time and (oldest is None or upload_time < oldest[0]):
            oldest = (upload_time, name, version)

    print(f"Dependencies checked: {checked}")
    print(f"Packages not on PyPI: {len(missing_packages)}")
    print(f"Versions not on PyPI: {len(missing_versions)}")
    if oldest:
        t, name, version = oldest
        print(f"Oldest pinned release: {name}={version} ({t[:4]})")
    else:
        print("Oldest pinned release: none")

    # Details, so you know exactly which lines to fix.
    for n in missing_packages:
        print(f"  [no such package] {n}")
    for v in missing_versions:
        print(f"  [no such version] {v}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "requirements.txt")