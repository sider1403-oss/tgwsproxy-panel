#!/usr/bin/env python3
"""Build GitHub Release notes for a tag from CHANGELOG.md.

Usage: release_notes.py v1.2.0

Prints a first line "TITLE: ..." followed by the markdown body.
Falls back to the commit list when the changelog has no section for the tag.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

REPO = "sider1403-oss/tgwsproxy-panel"


def changelog_section(version: str) -> tuple[str, str] | None:
    path = pathlib.Path("CHANGELOG.md")
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^##\s*\[" + re.escape(version) + r"\][^\n]*\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    return "TGWSProxy panel " + version, match.group(1).strip()


def commit_list(tag: str) -> tuple[str, str]:
    try:
        prev = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", tag + "^"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        prev = ""
    rng = f"{prev}..{tag}" if prev else tag
    log = subprocess.run(
        ["git", "log", "--no-merges", "--pretty=format:- %s (%h)", rng],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return "TGWSProxy panel " + tag, "### Изменения\n\n" + (log or "- см. историю коммитов")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: release_notes.py <tag>", file=sys.stderr)
        return 2
    tag = sys.argv[1]
    version = tag[1:] if tag.startswith("v") else tag
    try:
        result = changelog_section(version) or commit_list(tag)
    except Exception:
        result = ("TGWSProxy panel " + version, "")
    title, body = result
    if not body:
        body = "Изменения см. в CHANGELOG.md."
    print(f"TITLE: {title}")
    print()
    print(body)
    print()
    print("---")
    print(
        f"**Полный список изменений:** https://github.com/{REPO}/compare/"
        f"v{version}...{tag}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
