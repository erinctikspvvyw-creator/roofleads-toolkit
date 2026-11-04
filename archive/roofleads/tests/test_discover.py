import httpx

from roofleads.discover import place_to_lead, wait_for_run
from roofleads.errors import ApiError
from roofleads.http_client import HttpClient
from roofleads.pipeline import discover_city
from roofleads.sample_data import build_sample_companies
from tests.conftest import make_runtime


def test_discover_request_disables_personal_data_addons(tmp_path, settings) -> None:
    runtime = make_runtime(tmp_path, settings, companies=build_sample_companies())
    discover_city(runtime, "Austin", set())
    assert runtime.fixtures is not None
    body = runtime.fixtures.run_inputs[0]
    assert body["searchStringsArray"] == ["roof repair Austin TX"]
    assert body["locationQuery"] == "Austin, Texas, USA"
    assert body["city"] == "Austin"
    assert body["state"] == "Texas"
    assert body["countryCode"] == "us"
    assert body["scrapeContacts"] is False
    assert body["maximumLeadsEnrichmentRecords"] == 0
    assert body["verifyLeadsEnrichmentEmails"] is False
    assert body["maxReviews"] == 0
    assert body["maxImages"] == 0
    assert body["maxQuestions"] == 0
    assert body["scrapeReviewsPersonalData"] is False
    assert body["scrapeSocialMediaProfiles"] == {
        "facebooks": False,
        "instagrams": False,
        "youtubes": False,
        "tiktoks": False,
        "twitters": False,
    }
    assert body["scrapePlaceDetailPage"] is False
    runtime.http.close()


def test_place_parser_keeps_business_fields_only() -> None:
    lead, reason = place_to_lead(
        {
            "title": "Cedar Post Roofing",
            "website": "https://cedarpostroof.example",
            "phoneUnformatted": "5125550140",
            "city": "Austin",
            "state": "Texas",
            "placeId": "plc-1",
            "reviews": [{"reviewerName": "should-not-persist"}],
            "leadsEnrichment": [{"linkedin": "https://www.linkedin.com/in/should-not-persist"}],
        },
        fallback_city="Austin",
        source="apify:test+hunter:domain-search",
    )
    assert reason == ""
    assert lead is not None
    record = lead.to_record()
    assert "should-not-persist" not in str(record)
    assert "linkedin" not in record
    outside, why = place_to_lead({"title": "Sooner", "state": "Oklahoma"}, fallback_city="Austin", source="x")
    assert outside is None and why == "outside_area"
    blank, why_blank = place_to_lead({"title": "  "}, fallback_city="Austin", source="x")
    assert blank is None and why_blank == "no_name"


def test_polling_stops_on_success_and_on_timeout() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        status = "RUNNING" if calls["n"] < 3 else "SUCCEEDED"
        return httpx.Response(200, json={"data": {"id": "run-1", "status": status, "defaultDatasetId": "ds-1"}})

    clock = {"t": 0.0}

    def sleeper(seconds: float) -> None:
        clock["t"] += seconds

    client = HttpClient(transport=httpx.MockTransport(handler), sleeper=lambda _seconds: None)
    finished = wait_for_run(
        client,
        "run-1",
        "",
        timeout_seconds=30,
        poll_seconds=5,
        monotonic=lambda: clock["t"],
        sleeper=sleeper,
    )
    assert finished["status"] == "SUCCEEDED"
    assert calls["n"] == 3

    def running(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"id": "run-2", "status": "RUNNING", "defaultDatasetId": ""}})

    clock["t"] = 0.0
    client = HttpClient(transport=httpx.MockTransport(running), sleeper=lambda _seconds: None)
    try:
        wait_for_run(
            client,
            "run-2",
            "secret-token",
            timeout_seconds=5,
            poll_seconds=5,
            monotonic=lambda: clock["t"],
            sleeper=sleeper,
        )
    except ApiError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected a timeout")
    assert "timed" in message.lower() or "still" in message.lower()
    assert "secret-token" not in message
