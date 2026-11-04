import hashlib
import json
from pathlib import Path
from typing import Any

from roofleads.budget import Budget
from roofleads.errors import ConfigError

CACHE_VERSION = 1


def stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class Cache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": CACHE_VERSION, "discover": {}, "domains": {}, "emails": {}, "spend": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Cache file {self.path} is unreadable ({exc}). "
                "Move it aside and run again. Companies that were only in the damaged file "
                "will be fetched again and may cost credits."
            ) from exc
        version = loaded.get("version") if isinstance(loaded, dict) else None
        if not isinstance(loaded, dict) or version != CACHE_VERSION:
            raise ConfigError(
                f"Cache file {self.path} has version {version!r}, "
                "which this program does not read. Move that file aside and run again. "
                "Companies in the old file will be fetched again and may cost credits."
            )
        loaded.setdefault("discover", {})
        loaded.setdefault("domains", {})
        loaded.setdefault("emails", {})
        loaded.setdefault("spend", {})
        return loaded

    def spend(self) -> tuple[int, int]:
        spend = self.data.get("spend") or {}
        return int(spend.get("hunter_credits") or 0), int(spend.get("apify_micro_usd") or 0)

    def get_discover(self, key: str) -> dict[str, Any] | None:
        value = self.data["discover"].get(key)
        return value if isinstance(value, dict) else None

    def set_discover(self, key: str, record: dict[str, Any]) -> None:
        self.data["discover"][key] = record

    def get_domain(self, domain: str) -> dict[str, Any] | None:
        value = self.data["domains"].get(domain)
        return value if isinstance(value, dict) else None

    def set_domain(self, domain: str, record: dict[str, Any]) -> None:
        self.data["domains"][domain] = record

    def get_email(self, email: str) -> dict[str, Any] | None:
        value = self.data["emails"].get(email)
        return value if isinstance(value, dict) else None

    def set_email(self, email: str, record: dict[str, Any]) -> None:
        self.data["emails"][email] = record

    def save(self, budget: Budget) -> None:
        self.data["spend"] = {
            "hunter_credits": budget.lifetime_hunter,
            "apify_micro_usd": budget.lifetime_apify_micro,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)
