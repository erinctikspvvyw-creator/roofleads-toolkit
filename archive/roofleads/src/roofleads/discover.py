from collections.abc import Callable
from typing import Any

from roofleads.budget import decimal_to_micro, micro_to_money
from roofleads.cache import stable_hash
from roofleads.config import Settings, render_template
from roofleads.errors import ApiError
from roofleads.http_client import HttpClient
from roofleads.models import Lead
from roofleads.normalize import tidy

_TEXAS = {"texas", "tx"}
_FAILED_RUN = {"FAILED", "ABORTED", "TIMED-OUT", "TIMING-OUT"}


def actor_api_id(actor_id: str) -> str:
    return actor_id.replace("/", "~")


def filter_count(settings: Settings) -> int:
    count = 0
    if settings.website_filter not in {"", "allPlaces"}:
        count += 1
    if settings.skip_closed_places:
        count += 1
    return count


def per_place_micro(settings: Settings) -> int:
    filters = filter_count(settings)
    return decimal_to_micro(settings.apify_usd_per_place + settings.apify_usd_per_filter * filters)


def estimate_run_micro(settings: Settings, term_count: int) -> int:
    places = settings.max_places_per_search * term_count
    return decimal_to_micro(settings.apify_usd_per_start) + per_place_micro(settings) * places


def actual_run_micro(settings: Settings, item_count: int) -> int:
    return decimal_to_micro(settings.apify_usd_per_start) + per_place_micro(settings) * item_count


def actor_input(settings: Settings, city: str) -> dict[str, object]:
    terms = tuple(render_template(term, city, "discover.search_terms") for term in settings.search_terms)
    location = render_template(settings.location_template, city, "discover.location_template")
    # Personal-data add-ons stay off. They collect profiles, inboxes, or reviewer
    # data and add per-item fees. Business emails come from Hunter instead.
    return {
        "searchStringsArray": list(terms),
        "locationQuery": location,
        "maxCrawledPlacesPerSearch": settings.max_places_per_search,
        "language": settings.language,
        "countryCode": settings.country_code,
        "city": city,
        "state": settings.state,
        "website": settings.website_filter,
        "skipClosedPlaces": settings.skip_closed_places,
        "scrapePlaceDetailPage": False,
        "scrapeContacts": False,
        "maximumLeadsEnrichmentRecords": 0,
        "verifyLeadsEnrichmentEmails": False,
        "maxReviews": 0,
        "maxImages": 0,
        "scrapeReviewsPersonalData": False,
        "maxQuestions": 0,
        "scrapeSocialMediaProfiles": {
            "facebooks": False,
            "instagrams": False,
            "youtubes": False,
            "tiktoks": False,
            "twitters": False,
        },
    }


def place_to_lead(item: dict[str, Any], *, fallback_city: str, source: str) -> tuple[Lead | None, str]:
    name = tidy(str(item.get("title") or ""))
    if not name:
        return None, "no_name"
    state = tidy(str(item.get("state") or ""))
    if state and state.lower() not in _TEXAS:
        return None, "outside_area"
    phone = str(item.get("phoneUnformatted") or item.get("phone") or "").strip()
    return (
        Lead(
            company_name=name,
            website=str(item.get("website") or "").strip(),
            phone=phone,
            city=tidy(str(item.get("city") or fallback_city)),
            place_id=str(item.get("placeId") or "").strip(),
            source=source,
        ),
        "",
    )


def _data(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    raise ApiError("Apify returned a run payload this tool could not read.")


def start_actor_run(http: HttpClient, settings: Settings, token: str, body: dict[str, object]) -> dict[str, Any]:
    url = f"https://api.apify.com/v2/acts/{actor_api_id(settings.actor_id)}/runs"
    params = {"token": token} if token else None
    payload = http.request_json("POST", url, params=params, json_body=body, group="apify")
    return _data(payload)


def get_actor_run(http: HttpClient, run_id: str, token: str) -> dict[str, Any]:
    params = {"token": token} if token else None
    payload = http.request_json(
        "GET",
        f"https://api.apify.com/v2/actor-runs/{run_id}",
        params=params,
        group="apify",
    )
    return _data(payload)


def wait_for_run(
    http: HttpClient,
    run_id: str,
    token: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> dict[str, Any]:
    started = monotonic()
    while True:
        run = get_actor_run(http, run_id, token)
        status = str(run.get("status") or "")
        if status == "SUCCEEDED":
            return run
        if status in _FAILED_RUN:
            raise ApiError(
                f"Apify run {run_id} ended with status {status}. "
                "No companies from that run were saved. "
                "Check the run in the Apify console, then run this command again."
            )
        if monotonic() - started >= timeout_seconds:
            raise ApiError(
                f"Apify run {run_id} was still {status or 'running'} after {int(timeout_seconds)} seconds. "
                "Wait and run the same command again. Completed city searches stay in the cache."
            )
        sleeper(poll_seconds)


def fetch_dataset_items(http: HttpClient, dataset_id: str, token: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    limit = 1000
    while True:
        params = {"offset": str(offset), "limit": str(limit), "clean": "true"}
        if token:
            params["token"] = token
        payload = http.request_json(
            "GET",
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            params=params,
            group="apify",
        )
        if isinstance(payload, list):
            page = [row for row in payload if isinstance(row, dict)]
        elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
            page = [row for row in payload["items"] if isinstance(row, dict)]
        else:
            raise ApiError("Apify dataset response was not a list of places.")
        items.extend(page)
        if len(page) < limit:
            return items
        offset += limit


def source_label(settings: Settings) -> str:
    return f"apify:{settings.actor_id}+hunter:domain-search"
