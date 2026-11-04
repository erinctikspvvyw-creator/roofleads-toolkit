import logging
from decimal import Decimal

import httpx

from roofleads.budget import Budget, decimal_to_micro, micro_to_money
from roofleads.errors import ApiError
from roofleads.http_client import HttpClient
from roofleads.logsetup import JsonFormatter, redact


def test_budget_stops_on_the_credit_that_would_pass_the_cap() -> None:
    budget = Budget(max_credits=2, max_apify_micro=decimal_to_micro(Decimal("1")))
    assert budget.can_afford_credits(1)
    budget.charge_credits(1)
    assert budget.can_afford_credits(1)
    budget.charge_credits(1)
    assert not budget.can_afford_credits(1)
    budget.stop_for_credits(1, "a Hunter verification")
    assert "max-credits" in (budget.stopped_reason or "")
    assert micro_to_money(120050) == "0.120050"


def test_retry_honors_retry_after_and_does_not_retry_a_rejected_key() -> None:
    secret = "super-secret-token"
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow"})
        if "fail" in str(request.url):
            return httpx.Response(401, json={"errors": [{"details": f"bad api_key={secret}"}]})
        return httpx.Response(200, json={"ok": True})

    slept: list[float] = []
    client = HttpClient(
        transport=httpx.MockTransport(handler),
        sleeper=slept.append,
        max_retries=3,
        secrets=[secret],
    )
    assert client.request_json("GET", "https://api.hunter.io/v2/domain-search", group="hunter") == {"ok": True}
    assert slept == [0]
    calls["n"] = 0

    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": [{"details": f"bad api_key={secret} token={secret}"}]})

    client._client = httpx.Client(transport=httpx.MockTransport(reject), trust_env=False, follow_redirects=False)
    try:
        client.request_json("GET", "https://api.hunter.io/v2/email-verifier", params={"api_key": secret}, group="hunter")
    except ApiError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected the rejected key to raise")
    assert secret not in message
    assert "HUNTER_API_KEY" in message
    assert redact(f"token={secret}", [secret]) == "token=REDACTED"


def test_server_error_is_retried_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(transport=httpx.MockTransport(handler), sleeper=lambda _seconds: None, max_retries=4)
    assert client.request_json("GET", "https://api.apify.com/v2/actor-runs/1", group="apify") == {"ok": True}
    assert calls["n"] == 3


def test_log_formatter_redacts_tokens() -> None:
    formatter = JsonFormatter(secrets=["super-secret-token"])
    record = logging.LogRecord("roofleads", 20, __file__, 1, "token=super-secret-token", (), None)
    rendered = formatter.format(record)
    assert "super-secret-token" not in rendered
    assert "REDACTED" in rendered
