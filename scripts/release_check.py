"""Read-only check for the latest stable GitHub release of Scope Recall."""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


RELEASES_API = "https://api.github.com/repos/410979729/scope-recall-hermes/releases?per_page=100"
RELEASE_PAGE = "https://github.com/410979729/scope-recall-hermes/releases/tag/{}"
VERSION_PATTERN = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def parse_version(value):
    """Return a numeric version tuple, rejecting shell or tag syntax."""
    match = VERSION_PATTERN.fullmatch(value.strip()) if isinstance(value, str) else None
    if not match:
        raise ValueError("invalid version")
    return tuple(int(part) for part in match.groups())


def read_current_version(env_file):
    """Read only the SCOPE_RECALL_VERSION setting from a Compose env file."""
    found = []
    for line in Path(env_file).read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*(?:export\s+)?SCOPE_RECALL_VERSION\s*=\s*(.*?)\s*$", line)
        if match:
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            found.append(value)
    if len(found) != 1:
        raise ValueError("SCOPE_RECALL_VERSION must appear exactly once")
    parse_version(found[0])
    return found[0].removeprefix("v")


def build_status(current, releases):
    current_version = parse_version(current)
    candidates = []
    for release in releases:
        if (
            not isinstance(release, dict)
            or release.get("draft") is not False
            or release.get("prerelease") is not False
        ):
            continue
        tag = release.get("tag_name")
        try:
            version = parse_version(tag)
        except ValueError:
            continue
        candidates.append((version, tag.strip()))
    if not candidates:
        raise ValueError("no valid stable release")
    latest_version, latest_tag = max(candidates, key=lambda item: item[0])
    return {
        "releaseURL": RELEASE_PAGE.format(latest_tag),
        "current": current.removeprefix("v"),
        "latest": latest_tag.removeprefix("v"),
        "update_available": latest_version > current_version,
    }


def check(current, opener=urllib.request.urlopen):
    request = urllib.request.Request(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "scope-recall-release-check"},
    )
    try:
        with opener(request, timeout=15) as response:
            releases = json.load(response)
        if not isinstance(releases, list):
            raise ValueError("unexpected release response")
        return build_status(current, releases)
    except (OSError, TimeoutError, urllib.error.URLError, UnicodeError, ValueError):
        return {
            "releaseURL": None,
            "current": current.removeprefix("v"),
            "latest": None,
            "update_available": None,
            "error": "release_check_failed",
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env", help="Compose env file containing SCOPE_RECALL_VERSION")
    args = parser.parse_args(argv)
    try:
        current = read_current_version(args.env_file)
    except (OSError, UnicodeError, ValueError):
        print(json.dumps({
            "releaseURL": None,
            "current": None,
            "latest": None,
            "update_available": None,
            "error": "invalid_local_version",
        }, separators=(",", ":")))
        return 2
    result = check(current)
    print(json.dumps(result, separators=(",", ":")))
    return 2 if result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
