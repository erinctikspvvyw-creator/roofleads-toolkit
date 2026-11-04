import time
from collections.abc import Callable
from typing import Any

import httpx

from roofleads.errors import ApiError
from roofleads.logsetup import redact

_REDIRECTS = {301, 302, 303, 307, 308}


class HttpClient:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] | None = None,
        monotonic: Callable[[], float] | None = None,
        max_retries: int = 4,
        secrets: list[str] | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._client = httpx.Client(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._sleeper = sleeper or time.sleep
        self._monotonic = monotonic or time.monotonic
        self._max_retries = max_retries
        self._secrets = [secret for secret in (secrets or []) if secret]
        self._intervals: dict[str, float] = {}
        self._next_ok: dict[str, float] = {}

    def close(self) -> None:
        self._client.close()

    def set_min_interval(self, group: str, seconds: float) -> None:
        self._intervals[group] = max(0.0, seconds)

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
        group: str = "default",
    ) -> Any:
        delay = 0.5
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            self._pace(group)
            try:
                response = self._client.request(method, url, params=params, json=json_body)
            except httpx.TransportError as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break
                self._sleeper(delay)
                delay = min(delay * 2, 30.0)
                continue
            if response.status_code in _REDIRECTS:
                raise ApiError(
                    "The API redirected a request. This tool does not follow redirects, "
                    "so an API key cannot be sent to another website. "
                    f"Host: {response.request.url.host}. Status: {response.status_code}."
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self._max_retries:
                    raise ApiError(self._rate_limit_message(response))
                self._sleeper(self._retry_wait(response, delay))
                delay = min(delay * 2, 30.0)
                continue
            if response.status_code >= 400:
                raise self._error_for(response)
            if response.status_code == 204 or not response.content:
                return {}
            try:
                return response.json()
            except ValueError as exc:
                raise ApiError(
                    f"The API at {response.request.url.host} returned a response that was not JSON."
                ) from exc
        raise ApiError(
            redact(
                f"Network error talking to the API after {self._max_retries} tries: {last_error}",
                self._secrets,
            )
        )

    def _pace(self, group: str) -> None:
        interval = self._intervals.get(group, 0.0)
        if interval <= 0:
            return
        now = self._monotonic()
        wait = self._next_ok.get(group, 0.0) - now
        if wait > 0:
            self._sleeper(wait)
        self._next_ok[group] = self._monotonic() + interval

    def _retry_wait(self, response: httpx.Response, fallback: float) -> float:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(float(retry_after), 30.0)
        return fallback

    def _rate_limit_message(self, response: httpx.Response) -> str:
        host = response.request.url.host
        if response.status_code == 429:
            return (
                f"{host} kept returning HTTP 429 after several retries. "
                "Wait a minute and run the same command again. "
                "Companies already in the local cache are not billed again."
            )
        return (
            f"{host} returned HTTP {response.status_code} after several retries. "
            "Wait a minute and run the same command again. "
            "Companies already in the local cache are not billed again."
        )

    def _error_for(self, response: httpx.Response) -> ApiError:
        host = response.request.url.host
        if response.status_code == 401 and "apify.com" in host:
            return ApiError("Apify rejected the token (HTTP 401). Check APIFY_TOKEN in your .env file.")
        if response.status_code == 401 and "hunter.io" in host:
            return ApiError("Hunter rejected the API key (HTTP 401). Check HUNTER_API_KEY in your .env file.")
        body = redact(response.text[:400], self._secrets)
        return ApiError(f"HTTP {response.status_code} from {host}{response.request.url.path}: {body}")
