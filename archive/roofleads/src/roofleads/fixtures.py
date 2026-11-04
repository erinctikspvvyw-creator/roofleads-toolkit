import json
import re
from typing import Any

import httpx

from roofleads.mx import MxResult
from roofleads.normalize import company_domain
from roofleads.sample_data import SampleCompany, build_sample_companies

BANNED_MARKER = "should-not-persist"
BANNED_PHONE = "+15125559999"

_RESULT = {
    "valid": "deliverable",
    "invalid": "undeliverable",
    "accept_all": "risky",
    "webmail": "risky",
    "disposable": "undeliverable",
    "unknown": "unknown",
}


class FixtureWorld:
    """Serves the bundled companies for --dry-run. No network and no API keys."""

    def __init__(self, companies: list[SampleCompany] | None = None) -> None:
        self.companies = list(companies) if companies is not None else build_sample_companies()
        self.calls: list[str] = []
        self.run_inputs: list[dict[str, Any]] = []
        self.searched_domains: list[str] = []
        self.verified_emails: list[str] = []
        self._runs: dict[str, str] = {}
        self._datasets: dict[str, str] = {}
        self._sequence = 0
        self.no_mx = {
            company_domain(company.website)
            for company in self.companies
            if not company.mx and company_domain(company.website)
        }
        self._by_email = {company.email.lower(): company for company in self.companies if company.email}

    def lookup(self, domain: str) -> MxResult:
        host = domain.lower().rstrip(".")
        if host in self.no_mx:
            return MxResult(False, ())
        return MxResult(True, ("mx.example",))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.host}{request.url.path}")
        host = request.url.host
        path = request.url.path
        if host == "api.apify.com" and path.endswith("/runs") and request.method == "POST":
            return self._start_run(request)
        if host == "api.apify.com" and path.startswith("/v2/actor-runs/"):
            run_id = path.rsplit("/", 1)[-1]
            dataset_id = self._runs.get(run_id, "")
            return httpx.Response(
                200,
                json={"data": {"id": run_id, "status": "SUCCEEDED", "defaultDatasetId": dataset_id}},
            )
        if host == "api.apify.com" and "/datasets/" in path and path.endswith("/items"):
            dataset_id = path.split("/datasets/", 1)[1].split("/", 1)[0]
            city = self._datasets.get(dataset_id, "")
            return httpx.Response(200, json=[self._place(company) for company in self.companies if company.city == city])
        if host == "api.hunter.io" and path == "/v2/domain-search":
            domain = request.url.params.get("domain", "")
            self.searched_domains.append(domain)
            emails = self._emails_for(domain)
            return httpx.Response(
                200,
                json={"data": {"domain": domain, "emails": emails}, "meta": {"results": len(emails)}},
            )
        if host == "api.hunter.io" and path == "/v2/email-verifier":
            email = request.url.params.get("email", "")
            self.verified_emails.append(email)
            return httpx.Response(200, json=self._verifier(email))
        raise RuntimeError(f"no fixture for {request.method} {request.url}")

    def _start_run(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode() or "{}")
        self.run_inputs.append(body)
        self._sequence += 1
        run_id = f"run-{self._sequence}"
        dataset_id = f"dataset-{self._sequence}"
        city = str(body.get("city") or "")
        self._runs[run_id] = dataset_id
        self._datasets[dataset_id] = city
        return httpx.Response(
            200,
            json={"data": {"id": run_id, "status": "SUCCEEDED", "defaultDatasetId": dataset_id}},
        )

    def _place(self, company: SampleCompany) -> dict[str, object]:
        return {
            "title": company.company_name,
            "website": company.website,
            "phone": company.phone,
            "phoneUnformatted": re.sub(r"\D", "", company.phone),
            "city": company.city,
            "state": company.state,
            "placeId": company.place_id,
            "reviews": [{"reviewerName": BANNED_MARKER}],
            "leadsEnrichment": [{"linkedin": f"https://www.linkedin.com/in/{BANNED_MARKER}", "phoneNumber": BANNED_PHONE}],
        }

    def _emails_for(self, domain: str) -> list[dict[str, object]]:
        emails: list[dict[str, object]] = []
        for company in self.companies:
            if company_domain(company.website) != domain or not company.email:
                continue
            emails.append(self._email_object(company))
        emails.append(
            {
                "value": "owner.personal@gmail.com",
                "type": "personal",
                "confidence": 99,
                "first_name": "Hidden",
                "last_name": "Person",
                "position": "Owner",
                "linkedin": f"https://www.linkedin.com/in/{BANNED_MARKER}",
                "twitter": BANNED_MARKER,
                "phone_number": BANNED_PHONE,
            }
        )
        return emails

    def _email_object(self, company: SampleCompany) -> dict[str, object]:
        parts = company.owner_name.split()
        first = parts[0] if parts else ""
        last = parts[-1] if len(parts) > 1 else ""
        return {
            "value": company.email,
            "type": company.email_type,
            "confidence": company.confidence,
            "first_name": first,
            "last_name": last,
            "position": company.owner_position,
            "linkedin": f"https://www.linkedin.com/in/{BANNED_MARKER}",
            "twitter": BANNED_MARKER,
            "phone_number": BANNED_PHONE,
        }

    def _verifier(self, email: str) -> dict[str, object]:
        company = self._by_email.get(email.lower())
        status = company.verify_status if company is not None else "unknown"
        if status not in _RESULT:
            status = "unknown"
        return {
            "data": {
                "email": email,
                "status": status,
                "result": _RESULT[status],
                "disposable": status == "disposable",
                "mx_records": True,
            }
        }
