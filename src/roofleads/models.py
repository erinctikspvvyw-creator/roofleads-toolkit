from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

EmailStatus = Literal["valid", "risky", "invalid", "unknown"]

CSV_COLUMNS = (
    "company_name",
    "owner_name",
    "email",
    "website",
    "phone",
    "city",
    "email_status",
    "source",
    "collected_at",
)


def utc_stamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Lead:
    company_name: str = ""
    owner_name: str = ""
    email: str = ""
    website: str = ""
    phone: str = ""
    city: str = ""
    email_status: str = ""
    source: str = ""
    collected_at: str = ""
    place_id: str = ""
    domain: str = ""
    seq: int = 0
    role_account: bool = False
    local_reason: str = ""
    hunter_status: str = ""
    confidence: int | None = None

    def to_record(self) -> dict[str, object]:
        return asdict(self)

    def to_public_row(self) -> dict[str, str]:
        return {key: str(getattr(self, key)) for key in CSV_COLUMNS}


def lead_from_record(row: dict[str, object]) -> Lead:
    confidence = row.get("confidence")
    parsed_confidence: int | None
    if confidence is None or confidence == "":
        parsed_confidence = None
    else:
        parsed_confidence = int(str(confidence))
    return Lead(
        company_name=str(row.get("company_name") or ""),
        owner_name=str(row.get("owner_name") or ""),
        email=str(row.get("email") or ""),
        website=str(row.get("website") or ""),
        phone=str(row.get("phone") or ""),
        city=str(row.get("city") or ""),
        email_status=str(row.get("email_status") or ""),
        source=str(row.get("source") or ""),
        collected_at=str(row.get("collected_at") or ""),
        place_id=str(row.get("place_id") or ""),
        domain=str(row.get("domain") or ""),
        seq=int(str(row.get("seq") or 0)),
        role_account=bool(row.get("role_account") or False),
        local_reason=str(row.get("local_reason") or ""),
        hunter_status=str(row.get("hunter_status") or ""),
        confidence=parsed_confidence,
    )


@dataclass
class RunStats:
    discover_runs: int = 0
    discover_cached_runs: int = 0
    discover_places: int = 0
    discover_skipped_no_name: int = 0
    discover_skipped_outside_area: int = 0
    discover_duplicate_places: int = 0
    enrich_attempted: int = 0
    enrich_with_email: int = 0
    enrich_no_email: int = 0
    enrich_skipped_no_domain: int = 0
    enrich_skipped_shared_host: int = 0
    enrich_skipped_disposable_domain: int = 0
    enrich_cache_hits: int = 0
    enrich_api_calls: int = 0
    enrich_credits: int = 0
    verify_attempted: int = 0
    verify_local_invalid: int = 0
    verify_local_unknown: int = 0
    verify_cache_hits: int = 0
    verify_api_calls: int = 0
    verify_credits: int = 0
    verify_role_flagged: int = 0
    verify_skipped_role_policy: int = 0
    verify_smtp_rejected: int = 0
    status_counts: dict[str, int] = field(
        default_factory=lambda: {"valid": 0, "risky": 0, "invalid": 0, "unknown": 0}
    )
    dropped_not_valid: int = 0
    dropped_missing: int = 0
    dupes_email: int = 0
    dupes_domain: int = 0
    dupes_phone: int = 0
    clean_kept: int = 0
    delivered: int = 0
    credits_saved_by_cache: int = 0
    cities_exhausted: bool = False

    def bump_status(self, status: str) -> None:
        if status not in self.status_counts:
            self.status_counts[status] = 0
        self.status_counts[status] += 1

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
