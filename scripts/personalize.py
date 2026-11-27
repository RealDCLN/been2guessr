#!/usr/bin/env python3
"""Replace the ``your-username`` placeholder with a real GitHub username.

Usage:
    python scripts/personalize.py <github-username>
    python scripts/personalize.py <github-username> --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "your-username"

TARGETS = [
    ROOT / "README.md",
    ROOT / "pyproject.toml",
    ROOT / "src" / "been2guessr" / "beeneverywhere.py",
    ROOT / "src" / "been2guessr" / "web" / "static" / "index.html",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="GitHub username or organisation")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    username = args.username.strip().lstrip("@")
    if not username or "/" in username or " " in username:
        print("error: pass a plain GitHub username, e.g. octocat", file=sys.stderr)
        return 2

    changed = 0
    for path in TARGETS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        updated = text.replace(PLACEHOLDER, username)
        if updated == text:
            continue
        changed += 1
        if args.dry_run:
            print(f"would update {path.relative_to(ROOT)}")
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"updated {path.relative_to(ROOT)}")

    if not changed:
        print("nothing to do (placeholder already replaced?)")
    elif args.dry_run:
        print(f"{changed} file(s) would change")
    else:
        print(f"{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
