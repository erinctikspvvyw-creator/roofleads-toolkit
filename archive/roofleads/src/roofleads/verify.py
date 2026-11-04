import logging
import smtplib
from dataclasses import dataclass
from typing import Never, Protocol

from roofleads.disposable import domain_is_disposable
from roofleads.models import EmailStatus
from roofleads.mx import MxResult
from roofleads.normalize import is_role_address, syntax_ok

logger = logging.getLogger("roofleads")


class MxLookup(Protocol):
    def lookup(self, domain: str) -> MxResult: ...


class HunterVerdict:
    """String constants kept as a closed set for the status match below."""

    VALID = "valid"
    INVALID = "invalid"
    ACCEPT_ALL = "accept_all"
    WEBMAIL = "webmail"
    DISPOSABLE = "disposable"
    UNKNOWN = "unknown"


_VERDICTS = {
    HunterVerdict.VALID,
    HunterVerdict.INVALID,
    HunterVerdict.ACCEPT_ALL,
    HunterVerdict.WEBMAIL,
    HunterVerdict.DISPOSABLE,
    HunterVerdict.UNKNOWN,
}


def _assert_never(value: Never) -> Never:
    raise RuntimeError(f"Unexpected Hunter verdict: {value!r}")


@dataclass(frozen=True)
class LocalCheck:
    passed: bool
    status_if_failed: EmailStatus
    reason: str
    role_account: bool
    mx_hosts: tuple[str, ...]


def local_check(email: str, mx: MxLookup, disposable: set[str]) -> LocalCheck:
    role = is_role_address(email)
    if not syntax_ok(email):
        return LocalCheck(False, "invalid", "syntax", False, ())
    domain = email.rsplit("@", 1)[1]
    if domain_is_disposable(domain, disposable):
        return LocalCheck(False, "invalid", "disposable", role, ())
    looked = mx.lookup(domain)
    if looked.ok is False:
        return LocalCheck(False, "invalid", "no_mx", role, ())
    if looked.ok is None:
        return LocalCheck(False, "unknown", "mx_lookup_failed", role, ())
    return LocalCheck(True, "unknown", "", role, looked.hosts)


def parse_verdict(raw: str) -> str:
    status = raw.strip().lower()
    if status in _VERDICTS:
        return status
    logger.warning(
        "Hunter returned an unrecognized status; treating it as unknown",
        extra={"fields": {"event": "verify.unknown_status", "status": raw[:40]}},
    )
    return HunterVerdict.UNKNOWN


def verdict_from_payload(payload: object) -> str:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}
    if data.get("disposable") is True:
        return HunterVerdict.DISPOSABLE
    status = str(data.get("status") or "").strip()
    if status:
        return parse_verdict(status)
    result = str(data.get("result") or "").strip().lower()
    if result == "deliverable":
        return HunterVerdict.VALID
    if result == "undeliverable":
        return HunterVerdict.INVALID
    if result == "risky":
        return HunterVerdict.ACCEPT_ALL
    return HunterVerdict.UNKNOWN


def status_from_verdict(verdict: str) -> EmailStatus:
    match verdict:
        case HunterVerdict.VALID:
            return "valid"
        case HunterVerdict.INVALID:
            return "invalid"
        case HunterVerdict.DISPOSABLE:
            return "invalid"
        case HunterVerdict.ACCEPT_ALL:
            return "risky"
        case HunterVerdict.WEBMAIL:
            return "risky"
        case HunterVerdict.UNKNOWN:
            return "unknown"
        case _ as unexpected:
            _assert_never(unexpected)


def smtp_rcpt_probe(email: str, mail_host: str, *, timeout: float = 8.0) -> str:
    """Optional SMTP RCPT check. Off unless the operator passes --smtp-probe.

    Many providers treat unsolicited RCPT probes as abuse, home and cloud
    networks often block port 25, and greylisting makes the answer unreliable.
    Hunter's verifier is the check that decides whether a row is delivered.
    """
    if not mail_host:
        return "unknown"
    try:
        with smtplib.SMTP(mail_host, 25, timeout=timeout) as smtp:
            smtp.ehlo("roofleads.local")
            smtp.mail("")
            code, _message = smtp.rcpt(email)
    except (OSError, smtplib.SMTPException):
        return "unknown"
    if 200 <= code < 300:
        return "accepted"
    if 500 <= code < 600:
        return "rejected"
    return "unknown"
