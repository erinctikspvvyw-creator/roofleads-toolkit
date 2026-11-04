#!/usr/bin/env python3
"""Offline demo: prints toolkit layout check. No network."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    required = [
        ROOT / "README.md",
        ROOT / "scripts",
        ROOT / "docs",
        ROOT / ".gitignore",
        ROOT / ".env.example",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        raise SystemExit(f"missing: {missing}")
    print("tiktok-shop-toolkit OK")
    print("Next: set APIFY_TOKEN in .env and run scripts/apify_*.py")


if __name__ == "__main__":
    main()
