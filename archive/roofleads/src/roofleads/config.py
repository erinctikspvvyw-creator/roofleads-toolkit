import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from roofleads.errors import ConfigError

DEFAULT_CITIES = (
    "Austin",
    "Houston",
    "Dallas",
    "San Antonio",
    "Fort Worth",
    "El Paso",
    "Arlington",
    "Corpus Christi",
    "Plano",
    "Lubbock",
    "Laredo",
    "Irving",
)


@dataclass(frozen=True)
class Settings:
    actor_id: str = "compass/crawler-google-places"
    search_terms: tuple[str, ...] = ("roof repair {city} TX",)
    cities: tuple[str, ...] = DEFAULT_CITIES
    location_template: str = "{city}, Texas, USA"
    state: str = "Texas"
    country_code: str = "us"
    max_places_per_search: int = 20
    website_filter: str = "withWebsite"
    skip_closed_places: bool = True
    language: str = "en"
    min_confidence: int = 50
    prefer_role_emails: bool = True
    reject_role_accounts: bool = False
    smtp_probe: bool = False
    disposable_domains_file: str = ""
    max_credits: int = 500
    max_apify_usd: Decimal = Decimal("5")
    hunter_usd_per_credit: Decimal = Decimal("0.10")
    hunter_credits_per_domain_search: int = 1
    hunter_credits_per_verification: int = 1
    apify_usd_per_place: Decimal = Decimal("0.004")
    apify_usd_per_filter: Decimal = Decimal("0.001")
    apify_usd_per_start: Decimal = Decimal("0.00005")
    hunter_min_interval_seconds: float = 0.25
    apify_min_interval_seconds: float = 1.0
    apify_poll_seconds: float = 5.0
    apify_run_timeout_seconds: float = 600.0
    max_retries: int = 4


def _section(raw: dict[str, object], name: str) -> dict[str, object]:
    value = raw.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] in the config must be a table.")
    return value


def _text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ConfigError(f"{label} must be a list of non-empty strings.")
    return tuple(item.strip() for item in value)


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ConfigError(f"{label} must be a number or a numeric string.")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ConfigError(f"{label} must be a number or a numeric string.") from exc
    if number < 0:
        raise ConfigError(f"{label} cannot be negative.")
    return number


def _int(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, int):
        raise ConfigError(f"{label} must be a whole number.")
    if value < minimum:
        raise ConfigError(f"{label} must be at least {minimum}.")
    return value


def load_settings(path: Path) -> Settings:
    if not path.exists():
        raise ConfigError(
            f"Config file not found: {path}. Run this command from the project folder, "
            "or pass --config with the path to roofleads.toml."
        )
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Could not read {path}: the file must be a TOML table.")

    discover = _section(raw, "discover")
    enrich = _section(raw, "enrich")
    verify = _section(raw, "verify")
    budget = _section(raw, "budget")
    limits = _section(raw, "limits")
    defaults = Settings()

    actor_id = str(discover.get("actor_id", defaults.actor_id)).strip()
    if "/" not in actor_id:
        raise ConfigError(
            f"discover.actor_id {actor_id!r} should look like compass/crawler-google-places."
        )
    website_filter = str(discover.get("website_filter", defaults.website_filter))
    if website_filter not in {"allPlaces", "withWebsite", "withoutWebsite"}:
        raise ConfigError(
            "discover.website_filter must be allPlaces, withWebsite, or withoutWebsite."
        )

    return Settings(
        actor_id=actor_id,
        search_terms=_text_tuple(discover.get("search_terms", list(defaults.search_terms)), "discover.search_terms"),
        cities=_text_tuple(discover.get("cities", list(defaults.cities)), "discover.cities"),
        location_template=str(discover.get("location_template", defaults.location_template)),
        state=str(discover.get("state", defaults.state)),
        country_code=str(discover.get("country_code", defaults.country_code)),
        max_places_per_search=_int(
            discover.get("max_places_per_search", defaults.max_places_per_search),
            "discover.max_places_per_search",
            minimum=1,
        ),
        website_filter=website_filter,
        skip_closed_places=bool(discover.get("skip_closed_places", defaults.skip_closed_places)),
        language=str(discover.get("language", defaults.language)),
        min_confidence=_int(enrich.get("min_confidence", defaults.min_confidence), "enrich.min_confidence", minimum=0),
        prefer_role_emails=bool(enrich.get("prefer_role_emails", defaults.prefer_role_emails)),
        reject_role_accounts=bool(verify.get("reject_role_accounts", defaults.reject_role_accounts)),
        smtp_probe=bool(verify.get("smtp_probe", defaults.smtp_probe)),
        disposable_domains_file=str(verify.get("disposable_domains_file", "")),
        max_credits=_int(budget.get("max_credits", defaults.max_credits), "budget.max_credits", minimum=0),
        max_apify_usd=_decimal(budget.get("max_apify_usd", defaults.max_apify_usd), "budget.max_apify_usd"),
        hunter_usd_per_credit=_decimal(
            budget.get("hunter_usd_per_credit", defaults.hunter_usd_per_credit),
            "budget.hunter_usd_per_credit",
        ),
        hunter_credits_per_domain_search=_int(
            budget.get("hunter_credits_per_domain_search", defaults.hunter_credits_per_domain_search),
            "budget.hunter_credits_per_domain_search",
            minimum=0,
        ),
        hunter_credits_per_verification=_int(
            budget.get("hunter_credits_per_verification", defaults.hunter_credits_per_verification),
            "budget.hunter_credits_per_verification",
            minimum=0,
        ),
        apify_usd_per_place=_decimal(
            budget.get("apify_usd_per_place", defaults.apify_usd_per_place),
            "budget.apify_usd_per_place",
        ),
        apify_usd_per_filter=_decimal(
            budget.get("apify_usd_per_filter", defaults.apify_usd_per_filter),
            "budget.apify_usd_per_filter",
        ),
        apify_usd_per_start=_decimal(
            budget.get("apify_usd_per_start", defaults.apify_usd_per_start),
            "budget.apify_usd_per_start",
        ),
        hunter_min_interval_seconds=float(limits.get("hunter_min_interval_seconds", defaults.hunter_min_interval_seconds)),
        apify_min_interval_seconds=float(limits.get("apify_min_interval_seconds", defaults.apify_min_interval_seconds)),
        apify_poll_seconds=float(limits.get("apify_poll_seconds", defaults.apify_poll_seconds)),
        apify_run_timeout_seconds=float(limits.get("apify_run_timeout_seconds", defaults.apify_run_timeout_seconds)),
        max_retries=_int(limits.get("max_retries", defaults.max_retries), "limits.max_retries", minimum=1),
    )


def render_template(template: str, city: str, label: str) -> str:
    try:
        return template.format(city=city)
    except (KeyError, IndexError, ValueError) as exc:
        raise ConfigError(
            f"{label} {template!r} could not be filled in for {city}. Use {{city}} as the only placeholder."
        ) from exc
