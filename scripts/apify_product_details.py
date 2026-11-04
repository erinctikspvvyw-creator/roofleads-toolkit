#!/usr/bin/env python3
"""Call unseenuser TikTok Shop product_details (+ related videos)."""
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
    p.add_argument("--region", default="US")
    args = p.parse_args()
    urls = [ln.strip() for ln in Path(args.urls_file).read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    if not urls:
        raise SystemExit("no urls")
    # Convert shop.tiktok.com/us/pdp/... to www.tiktok.com/shop/pdp/... if needed by actor
    product_urls = []
    for u in urls:
        if "shop.tiktok.com" in u and "/pdp/" in u:
            pid = u.rstrip("/").split("/")[-1]
            product_urls.append(f"https://www.tiktok.com/shop/pdp/{pid}")
        else:
            product_urls.append(u)
    run = run_actor(
        "unseenuser~TikTok-Shop-Scraper",
        {
            "mode": "product_details",
            "productUrls": product_urls,
            "region": args.region,
            "getRelatedVideos": True,
            "maxResults": len(product_urls),
        },
        wait_secs=600,
    )
    items = dataset_items(run["defaultDatasetId"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    print(f"wrote {len(items)} items -> {out}")


if __name__ == "__main__":
    main()
