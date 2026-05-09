#!/usr/bin/env python3
"""Validate the marketplace.json file against the plugin schema.

This script checks that all entries in .claude-plugin/marketplace.json
are well-formed, have required fields, and reference valid GitHub repositories.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

MARKETPLACE_PATH = Path(".claude-plugin/marketplace.json")

REQUIRED_PLUGIN_FIELDS = {
    "name",
    "description",
    "repo",
    "sha",
    "type",
}

VALID_PLUGIN_TYPES = {"agent", "skill", "command"}

GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def load_marketplace(path: Path) -> Any:
    """Load and parse the marketplace JSON file."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Marketplace file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def validate_plugin(index: int, plugin: Any) -> list[str]:
    """Validate a single plugin entry. Returns a list of error messages."""
    errors: list[str] = []
    prefix = f"Plugin[{index}]"

    if not isinstance(plugin, dict):
        return [f"{prefix}: expected an object, got {type(plugin).__name__}"]

    name = plugin.get("name", f"<index {index}>")
    prefix = f"Plugin '{name}'"

    # Check required fields
    for field in REQUIRED_PLUGIN_FIELDS:
        if field not in plugin:
            errors.append(f"{prefix}: missing required field '{field}'")

    # Validate type
    plugin_type = plugin.get("type")
    if plugin_type is not None and plugin_type not in VALID_PLUGIN_TYPES:
        errors.append(
            f"{prefix}: invalid type '{plugin_type}', "
            f"must be one of {sorted(VALID_PLUGIN_TYPES)}"
        )

    # Validate repo format
    repo = plugin.get("repo")
    if repo is not None:
        if not isinstance(repo, str) or not GITHUB_REPO_RE.match(repo):
            errors.append(
                f"{prefix}: 'repo' must be a GitHub owner/repo slug, got {repo!r}"
            )

    # Validate SHA format
    sha = plugin.get("sha")
    if sha is not None:
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            errors.append(
                f"{prefix}: 'sha' must be a 40-character hex string, got {sha!r}"
            )

    # Validate description is non-empty string
    description = plugin.get("description")
    if description is not None:
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{prefix}: 'description' must be a non-empty string")

    # Validate name is non-empty string
    if "name" in plugin:
        if not isinstance(plugin["name"], str) or not plugin["name"].strip():
            errors.append(f"{prefix}: 'name' must be a non-empty string")

    # Optional: validate tags if present
    tags = plugin.get("tags")
    if tags is not None:
        if not isinstance(tags, list):
            errors.append(f"{prefix}: 'tags' must be a list")
        elif not all(isinstance(t, str) for t in tags):
            errors.append(f"{prefix}: all 'tags' entries must be strings")

    return errors


def check_duplicate_repos(plugins: list[Any]) -> list[str]:
    """Check for duplicate repo entries in the marketplace."""
    seen: dict[str, str] = {}
    errors: list[str] = []
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        repo = plugin.get("repo")
        name = plugin.get("name", "<unknown>")
        if repo is None:
            continue
        if repo in seen:
            errors.append(
                f"Duplicate repo '{repo}' found in plugins '{seen[repo]}' and '{name}'"
            )
        else:
            seen[repo] = name
    return errors


def main() -> None:
    data = load_marketplace(MARKETPLACE_PATH)

    if not isinstance(data, list):
        print("ERROR: marketplace.json must be a JSON array", file=sys.stderr)
        sys.exit(1)

    all_errors: list[str] = []

    for i, plugin in enumerate(data):
        all_errors.extend(validate_plugin(i, plugin))

    all_errors.extend(check_duplicate_repos(data))

    if all_errors:
        print(f"Found {len(all_errors)} validation error(s):\n", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"marketplace.json is valid ({len(data)} plugins checked).")


if __name__ == "__main__":
    main()
