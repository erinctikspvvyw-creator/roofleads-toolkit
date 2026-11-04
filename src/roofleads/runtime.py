import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from roofleads.budget import Budget, decimal_to_micro
from roofleads.cache import Cache
from roofleads.config import Settings
from roofleads.disposable import load_disposable
from roofleads.fixtures import FixtureWorld
from roofleads.http_client import HttpClient
from roofleads.models import RunStats
from roofleads.mx import DnsPythonMx
from roofleads.sample_data import SampleCompany
from roofleads.verify import MxLookup, smtp_rcpt_probe


@dataclass
class Runtime:
    settings: Settings
    http: HttpClient
    cache: Cache
    budget: Budget
    stats: RunStats
    mx: MxLookup
    clock: Callable[[], datetime]
    mode: str
    token: str
    hunter_key: str
    smtp_probe: Callable[..., str] | None
    disposable: set[str]
    log: logging.Logger
    say: Callable[[str], None]
    fixtures: FixtureWorld | None = None


def build_runtime(
    settings: Settings,
    *,
    cache_path: Path,
    mode: str,
    token: str = "",
    hunter_key: str = "",
    clock: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
    companies: list[SampleCompany] | None = None,
    say: Callable[[str], None] | None = None,
    secrets: list[str] | None = None,
) -> Runtime:
    cache = Cache(cache_path)
    lifetime_hunter, lifetime_apify = cache.spend()
    budget = Budget(
        max_credits=settings.max_credits,
        max_apify_micro=decimal_to_micro(settings.max_apify_usd),
        lifetime_hunter=lifetime_hunter,
        lifetime_apify_micro=lifetime_apify,
    )
    fixtures: FixtureWorld | None = None
    mx: MxLookup
    if mode == "dry-run":
        fixtures = FixtureWorld(companies)
        transport: httpx.BaseTransport | None = httpx.MockTransport(fixtures.handler)
        mx = fixtures
        token = ""
        hunter_key = ""
    else:
        transport = None
        mx = DnsPythonMx()
    http = HttpClient(
        transport=transport,
        sleeper=sleeper,
        monotonic=monotonic,
        max_retries=settings.max_retries,
        secrets=secrets,
    )
    if mode == "dry-run":
        http.set_min_interval("hunter", 0)
        http.set_min_interval("apify", 0)
    else:
        http.set_min_interval("hunter", settings.hunter_min_interval_seconds)
        http.set_min_interval("apify", settings.apify_min_interval_seconds)
    probe = smtp_rcpt_probe if settings.smtp_probe else None
    return Runtime(
        settings=settings,
        http=http,
        cache=cache,
        budget=budget,
        stats=RunStats(),
        mx=mx,
        clock=clock or (lambda: datetime.now(timezone.utc)),
        mode=mode,
        token=token,
        hunter_key=hunter_key,
        smtp_probe=probe,
        disposable=load_disposable(settings.disposable_domains_file),
        log=logging.getLogger("roofleads"),
        say=say or (lambda message: print(message, flush=True)),
        fixtures=fixtures,
    )
