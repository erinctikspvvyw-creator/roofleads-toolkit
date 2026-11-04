from dataclasses import replace
from decimal import Decimal

from roofleads.pipeline import run_pipeline
from roofleads.sample_data import (
    BAD_SYNTAX_EMAIL,
    DOMAIN_DISPOSABLE,
    DOMAIN_NO_MX,
    SampleCompany,
    build_sample_companies,
)
from tests.conftest import make_runtime


def _company(number: int) -> SampleCompany:
    return SampleCompany(
        company_name=f"Test Roofing {number}",
        city="Austin",
        phone=f"(512) 555-20{number:02d}",
        website=f"https://test-{number}.example",
        email=f"info@test-{number}.example",
        owner_name="Ada Owner",
        owner_position="Owner",
        email_type="generic",
        confidence=90,
        verify_status="valid",
        place_id=f"t-{number}",
    )


def test_credit_guard_stops_before_the_next_paid_call(tmp_path, settings) -> None:
    companies = [_company(1), _company(2), _company(3)]
    tuned = replace(settings, cities=("Austin",), max_credits=3, max_places_per_search=10)
    runtime = make_runtime(tmp_path, tuned, companies=companies)
    result = run_pipeline(runtime, tmp_path / "out", target_rows=10)
    assert runtime.fixtures is not None
    assert runtime.fixtures.searched_domains == ["test-1.example", "test-2.example"]
    assert runtime.fixtures.verified_emails == ["info@test-1.example"]
    assert result.delivered == 1
    assert result.stopped_reason is not None
    assert "max-credits" in result.stopped_reason
    assert result.report["budget"]["this_run"]["hunter_credits"] == 3
    runtime.http.close()


def test_apify_guard_does_not_start_a_run(tmp_path, settings) -> None:
    tuned = replace(settings, cities=("Austin",), max_apify_usd=Decimal("0"))
    runtime = make_runtime(tmp_path, tuned, companies=[_company(1)])
    result = run_pipeline(runtime, tmp_path / "out", target_rows=1)
    assert runtime.fixtures is not None
    assert runtime.fixtures.calls == []
    assert result.delivered == 0
    assert result.stopped_reason is not None
    assert "Apify" in result.stopped_reason
    runtime.http.close()


def test_second_run_uses_the_cache_and_does_not_call_the_apis(tmp_path, settings) -> None:
    companies = [_company(1), _company(2)]
    tuned = replace(settings, cities=("Austin",), max_credits=20, max_places_per_search=10)
    first = make_runtime(tmp_path, tuned, companies=companies)
    first_result = run_pipeline(first, tmp_path / "out1", target_rows=2)
    assert first.fixtures is not None
    assert first.fixtures.calls
    assert first_result.delivered == 2
    first.http.close()

    second = make_runtime(tmp_path, tuned, companies=companies)
    second_result = run_pipeline(second, tmp_path / "out2", target_rows=2)
    assert second.fixtures is not None
    assert second.fixtures.calls == []
    assert second_result.delivered == 2
    assert second_result.report["budget"]["this_run"]["hunter_credits"] == 0
    assert second_result.report["budget"]["this_run"]["apify_usd"] == "0.000000"
    assert (
        second_result.report["budget"]["lifetime"]["hunter_credits"]
        == first_result.report["budget"]["lifetime"]["hunter_credits"]
    )
    second.http.close()


def test_fixture_run_skips_free_rejections_and_personal_fields(tmp_path, settings) -> None:
    runtime = make_runtime(tmp_path, settings, companies=build_sample_companies())
    result = run_pipeline(runtime, tmp_path / "out", target_rows=5)
    assert runtime.fixtures is not None
    assert DOMAIN_DISPOSABLE not in runtime.fixtures.searched_domains
    assert "facebook.com" not in runtime.fixtures.searched_domains
    assert BAD_SYNTAX_EMAIL not in runtime.fixtures.verified_emails
    assert f"info@{DOMAIN_NO_MX}" not in runtime.fixtures.verified_emails
    cache_text = (tmp_path / "cache.json").read_text(encoding="utf-8")
    discovered = (tmp_path / "out" / "discovered.jsonl").read_text(encoding="utf-8")
    assert "should-not-persist" not in cache_text
    assert "should-not-persist" not in discovered
    assert "+15125559999" not in cache_text
    assert "Hidden" not in cache_text
    assert result.delivered == 5
    runtime.http.close()
