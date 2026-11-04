"""Minimal Apify REST helpers. Token from APIFY_TOKEN env."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


API = "https://api.apify.com/v2"


def token() -> str:
    t = os.environ.get("APIFY_TOKEN", "").strip()
    if not t:
        raise SystemExit("Set APIFY_TOKEN in env or .env")
    return t


def _req(method: str, path: str, body: dict | None = None) -> Any:
    url = f"{API}{path}"
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise SystemExit(f"Apify HTTP {e.code}: {detail}") from e


def run_actor(actor_id: str, run_input: dict, wait_secs: int = 300) -> dict:
    """actor_id like username~name (tilde). Returns run object when succeeded."""
    encoded = urllib.parse.quote(actor_id, safe="")
    started = _req("POST", f"/acts/{encoded}/runs", run_input)
    run = started.get("data") or started
    run_id = run["id"]
    deadline = time.time() + wait_secs
    while time.time() < deadline:
        info = _req("GET", f"/actor-runs/{run_id}")
        run = info.get("data") or info
        status = run.get("status")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            if status != "SUCCEEDED":
                raise SystemExit(f"Run {run_id} ended: {status}")
            return run
        time.sleep(5)
    raise SystemExit(f"Run {run_id} still not terminal after {wait_secs}s")


def dataset_items(dataset_id: str, limit: int = 1000) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:
        page = _req(
            "GET",
            f"/datasets/{dataset_id}/items?format=json&clean=1&limit=100&offset={offset}",
        )
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        if len(page) < 100 or len(out) >= limit:
            break
        offset += 100
    return out[:limit]
