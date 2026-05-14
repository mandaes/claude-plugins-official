#!/usr/bin/env python3
"""
sync-marketplace.py

Syncs the local marketplace.json with the upstream anthropics/claude-plugins-official
repository, merging any new or updated plugin entries while preserving local
overrides (e.g. pinned SHAs, local-only plugins).

Usage:
    python sync-marketplace.py [--dry-run] [--upstream-url URL]
"""

import argparse
import json
import os
import sys
import urllib.request
from copy import deepcopy
from typing import Any

UPSTREAM_DEFAULT = (
    "https://raw.githubusercontent.com/anthropics/claude-plugins-official"
    "/main/.claude-plugin/marketplace.json"
)

MARKETPLACE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", ".claude-plugin", "marketplace.json"
)


def fetch_upstream(url: str) -> dict[str, Any]:
    """Fetch and parse the upstream marketplace.json."""
    print(f"Fetching upstream marketplace from: {url}")
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        raw = resp.read().decode()
    return json.loads(raw)


def load_local(path: str) -> dict[str, Any]:
    """Load the local marketplace.json."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_local(path: str, data: dict[str, Any]) -> None:
    """Write updated marketplace.json with consistent formatting."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")  # POSIX newline at EOF


def index_plugins(marketplace: dict[str, Any]) -> dict[str, dict]:
    """Return a dict keyed by plugin repo URL for fast lookup."""
    return {p["repo"]: p for p in marketplace.get("plugins", [])}


def merge_marketplaces(
    local: dict[str, Any],
    upstream: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """
    Merge upstream plugins into local marketplace.

    Strategy:
    - New upstream plugins are appended.
    - Existing plugins keep their local values (e.g. pinned SHA) unless the
      upstream has a newer `updated_at` timestamp.
    - Plugins that exist only locally are left untouched.

    Returns the merged marketplace and a list of human-readable change messages.
    """
    merged = deepcopy(local)
    local_index = index_plugins(local)
    upstream_index = index_plugins(upstream)
    changes: list[str] = []

    for repo_url, up_plugin in upstream_index.items():
        if repo_url not in local_index:
            # Brand-new plugin — add it
            merged["plugins"].append(deepcopy(up_plugin))
            changes.append(f"ADD  {repo_url}")
        else:
            local_plugin = local_index[repo_url]
            up_ts = up_plugin.get("updated_at", "")
            lo_ts = local_plugin.get("updated_at", "")

            if up_ts > lo_ts:
                # Upstream is newer — update metadata but keep local SHA if pinned
                updated = deepcopy(up_plugin)
                if local_plugin.get("pinned_sha"):
                    updated["sha"] = local_plugin["sha"]
                    updated["pinned_sha"] = local_plugin["pinned_sha"]

                # Replace in-place inside merged["plugins"]
                for i, p in enumerate(merged["plugins"]):
                    if p["repo"] == repo_url:
                        merged["plugins"][i] = updated
                        break
                changes.append(f"UPDATE {repo_url} ({lo_ts} -> {up_ts})")

    # Update top-level metadata if upstream has a newer schema version
    up_schema = upstream.get("schema_version", 0)
    lo_schema = merged.get("schema_version", 0)
    if up_schema > lo_schema:
        merged["schema_version"] = up_schema
        changes.append(f"SCHEMA {lo_schema} -> {up_schema}")

    return merged, changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync marketplace with upstream.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print changes without writing to disk.",
    )
    parser.add_argument(
        "--upstream-url",
        default=UPSTREAM_DEFAULT,
        help="URL of the upstream marketplace.json.",
    )
    args = parser.parse_args()

    try:
        upstream = fetch_upstream(args.upstream_url)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Could not fetch upstream marketplace: {exc}", file=sys.stderr)
        return 1

    local_path = os.path.abspath(MARKETPLACE_PATH)
    try:
        local = load_local(local_path)
    except FileNotFoundError:
        print(f"ERROR: Local marketplace not found at {local_path}", file=sys.stderr)
        return 1

    merged, changes = merge_marketplaces(local, upstream)

    if not changes:
        print("Marketplace is already up-to-date. No changes needed.")
        return 0

    print(f"Found {len(changes)} change(s):")
    for msg in changes:
        print(f"  {msg}")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return 0

    save_local(local_path, merged)
    print(f"\nWrote updated marketplace to {local_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
