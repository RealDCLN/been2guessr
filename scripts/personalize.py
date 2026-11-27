#!/usr/bin/env python3
"""Point the GitHub links at a different account.

By default this replaces the ``github.com/your-username`` placeholder. When
rebranding an already-personalised fork, pass the current owner with ``--from``:

    python scripts/personalize.py --from RealDCLN my-new-name
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = "your-username"

TARGETS = [
    ROOT / "README.md",
    ROOT / "pyproject.toml",
    ROOT / "src" / "been2guessr" / "beeneverywhere.py",
    ROOT / "src" / "been2guessr" / "web" / "app.py",
    ROOT / "src" / "been2guessr" / "web" / "static" / "index.html",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="New GitHub username or organisation")
    parser.add_argument(
        "--from",
        dest="source",
        default=DEFAULT_SOURCE,
        help=f"Current owner to replace (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    username = args.username.strip().lstrip("@")
    source = args.source.strip().lstrip("@").strip("/")
    if not username or "/" in username or " " in username:
        print("error: pass a plain GitHub username, e.g. octocat", file=sys.stderr)
        return 2
    if not source or "/" in source or " " in source:
        print("error: --from must be a plain GitHub username", file=sys.stderr)
        return 2

    old = f"github.com/{source}"
    new = f"github.com/{username}"

    changed = 0
    for path in TARGETS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        updated = text.replace(old, new)
        if updated == text:
            continue
        changed += 1
        if args.dry_run:
            print(f"would update {path.relative_to(ROOT)}")
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"updated {path.relative_to(ROOT)}")

    if not changed:
        print(f"nothing to do (no github.com/{source} links found)")
    elif args.dry_run:
        print(f"{changed} file(s) would change")
    else:
        print(f"{changed} file(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
