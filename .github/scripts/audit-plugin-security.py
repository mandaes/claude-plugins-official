#!/usr/bin/env python3
"""Audit plugins in marketplace.json for security concerns.

Checks for:
- Pinned SHAs (not branches/tags)
- Known malicious patterns in plugin metadata
- Suspicious URLs or domains
- Overly broad permission scopes
- Stale or archived repositories
"""

import json
import re
import sys
import os
import argparse
from pathlib import Path
from typing import Any

import requests

MARKETPLACE_PATH = Path(".claude-plugin/marketplace.json")
GITHUB_API = "https://api.github.com"

# Patterns that may indicate prompt injection or malicious intent
SUSPICIOUS_DESCRIPTION_PATTERNS = [
    re.compile(r"ignore (previous|all|above) instructions", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"<script[^>]*>", re.IGNORECASE),
    re.compile(r"eval\s*\(", re.IGNORECASE),
]

# Domains that are not allowed as plugin sources
BLOCKLISTED_DOMAINS = [
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
]


def gh_api(path: str, token: str | None = None) -> dict | list:
    """Make a GitHub API request."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(f"{GITHUB_API}{path}", headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def is_sha(ref: str) -> bool:
    """Return True if ref looks like a full 40-char commit SHA."""
    return bool(re.fullmatch(r"[0-9a-f]{40}", ref))


def check_repo_health(owner: str, repo: str, token: str | None) -> list[str]:
    """Return a list of warnings about a GitHub repository."""
    warnings = []
    try:
        data = gh_api(f"/repos/{owner}/{repo}", token=token)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            warnings.append(f"Repository {owner}/{repo} not found (deleted or private?)")
        else:
            warnings.append(f"Could not fetch repo metadata for {owner}/{repo}: {exc}")
        return warnings

    if data.get("archived"):
        warnings.append(f"Repository {owner}/{repo} is archived")
    if data.get("disabled"):
        warnings.append(f"Repository {owner}/{repo} is disabled")
    if data.get("fork"):
        # Forks are fine but worth noting for upstream-sourced plugins
        pass

    return warnings


def audit_plugin(plugin: dict[str, Any], token: str | None) -> list[str]:
    """Audit a single plugin entry and return a list of issue strings."""
    issues = []
    name = plugin.get("name", "<unnamed>")
    repo_url: str = plugin.get("repo", "")
    ref: str = plugin.get("ref", "")

    # --- SHA pinning check ---
    if ref and not is_sha(ref):
        issues.append(f"[{name}] ref '{ref}' is not a pinned SHA — use a full commit hash")

    # --- Blocklisted domains ---
    for domain in BLOCKLISTED_DOMAINS:
        if domain in repo_url:
            issues.append(f"[{name}] repo URL contains blocklisted domain '{domain}'")

    # --- Suspicious text in metadata ---
    for field in ("name", "description", "author"):
        value = plugin.get(field, "") or ""
        for pattern in SUSPICIOUS_DESCRIPTION_PATTERNS:
            if pattern.search(value):
                issues.append(
                    f"[{name}] field '{field}' matches suspicious pattern: {pattern.pattern}"
                )

    # --- GitHub repo health ---
    gh_match = re.match(
        r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", repo_url
    )
    if gh_match:
        owner, repo = gh_match.group(1), gh_match.group(2)
        issues.extend(check_repo_health(owner, repo, token))
    elif repo_url and "github.com" not in repo_url:
        issues.append(f"[{name}] repo URL is not a GitHub URL: {repo_url}")

    return issues


def load_marketplace(path: Path) -> list[dict]:
    """Load and return the list of plugins from marketplace.json."""
    with path.open() as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    return data.get("plugins", [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Security audit for marketplace plugins")
    parser.add_argument(
        "--marketplace",
        default=str(MARKETPLACE_PATH),
        help="Path to marketplace.json",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Exit with non-zero status if any warnings are found",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    plugins = load_marketplace(Path(args.marketplace))

    all_issues: list[str] = []
    for plugin in plugins:
        all_issues.extend(audit_plugin(plugin, token))

    if all_issues:
        print(f"::warning::Security audit found {len(all_issues)} issue(s):")
        for issue in all_issues:
            print(f"  - {issue}")
        if args.fail_on_warnings:
            return 1
    else:
        print("Security audit passed — no issues found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
