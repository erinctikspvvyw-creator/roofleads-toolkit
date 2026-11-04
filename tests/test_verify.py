import smtplib
from types import SimpleNamespace

import dns.exception
import dns.resolver

from roofleads.disposable import load_builtin_disposable
from roofleads.mx import DnsPythonMx, MxResult
from roofleads.verify import local_check, smtp_rcpt_probe, status_from_verdict, verdict_from_payload


class _Boom:
    def lookup(self, domain: str) -> MxResult:
        raise AssertionError(domain)


class _NoMx:
    def lookup(self, domain: str) -> MxResult:
        return MxResult(False, ())


class _YesMx:
    def lookup(self, domain: str) -> MxResult:
        return MxResult(True, ("mx.example",))


def test_free_checks_run_before_any_paid_lookup() -> None:
    disposable = load_builtin_disposable()
    syntax = local_check("not-an-email", _Boom(), disposable)
    assert syntax.passed is False and syntax.reason == "syntax"
    burned = local_check("person@mailinator.com", _Boom(), disposable)
    assert burned.passed is False and burned.reason == "disposable"
    missing = local_check("info@nomx.example", _NoMx(), disposable)
    assert missing.passed is False and missing.reason == "no_mx"
    role = local_check("info@roof.example", _YesMx(), disposable)
    assert role.passed is True and role.role_account is True


def test_hunter_status_map() -> None:
    assert status_from_verdict(verdict_from_payload({"data": {"status": "valid"}})) == "valid"
    assert status_from_verdict(verdict_from_payload({"data": {"status": "accept_all"}})) == "risky"
    assert status_from_verdict(verdict_from_payload({"data": {"status": "webmail"}})) == "risky"
    assert status_from_verdict(verdict_from_payload({"data": {"status": "invalid"}})) == "invalid"
    assert status_from_verdict(verdict_from_payload({"data": {"status": "unknown"}})) == "unknown"
    assert status_from_verdict(verdict_from_payload({"data": {"disposable": True, "status": "valid"}})) == "invalid"
    assert status_from_verdict(verdict_from_payload({"data": {"status": "brand-new"}})) == "unknown"


def test_mx_lookup_translates_dns_answers() -> None:
    class Resolver:
        def resolve(self, domain: str, rdtype: str) -> list[SimpleNamespace]:
            if domain == "missing.example":
                raise dns.resolver.NoAnswer
            if domain == "slow.example":
                raise dns.exception.Timeout
            return [SimpleNamespace(preference=10, exchange="mx.example.")]

    lookup = DnsPythonMx(resolver=Resolver())  # type: ignore[arg-type]
    assert lookup.lookup("roof.example").ok is True
    assert lookup.lookup("missing.example").ok is False
    assert lookup.lookup("slow.example").ok is None


def test_smtp_probe_maps_rcpt_codes(monkeypatch) -> None:
    class FakeSMTP:
        code = 550

        def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
            self.host = host

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def ehlo(self, name: str) -> tuple[int, bytes]:
            return (250, b"ok")

        def mail(self, sender: str) -> tuple[int, bytes]:
            return (250, b"ok")

        def rcpt(self, recipient: str) -> tuple[int, bytes]:
            return (self.code, b"no")

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    assert smtp_rcpt_probe("info@roof.example", "mx.example") == "rejected"
    FakeSMTP.code = 250
    assert smtp_rcpt_probe("info@roof.example", "mx.example") == "accepted"
