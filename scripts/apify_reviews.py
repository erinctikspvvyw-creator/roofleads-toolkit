#!/usr/bin/env python3
"""Call pro100chok TikTok Shop reviews scrape."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apify_common import dataset_items, run_actor

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--urls-file", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-reviews", type=int, default=40)
    p.add_argument("--region", default="us")
    args = p.parse_args()
    urls = [ln.strip() for ln in Path(args.urls_file).read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    run = run_actor(
        "pro100chok~tiktok-shop-scraper-usage",
        {
            "region": args.region,
            "scrapeType": "reviews",
            "reviewProductUrls": urls,
            "maxReviews": args.max_reviews,
            "reviewsSortBy": "recommended",
        },
        wait_secs=900,
    )
    items = dataset_items(run["defaultDatasetId"], limit=5000)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    print(f"wrote {len(items)} items -> {out}")


if __name__ == "__main__":
    main()
