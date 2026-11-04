from dataclasses import dataclass

import dns.exception
import dns.resolver


@dataclass(frozen=True)
class MxResult:
    """ok is True when MX records exist, False when they do not, None on a temporary failure."""

    ok: bool | None
    hosts: tuple[str, ...] = ()


class DnsPythonMx:
    def __init__(self, resolver: dns.resolver.Resolver | None = None) -> None:
        self._resolver = resolver if resolver is not None else dns.resolver.Resolver()
        self._resolver.lifetime = 5.0

    def lookup(self, domain: str) -> MxResult:
        try:
            answers = self._resolver.resolve(domain, "MX")
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return MxResult(False, ())
        except (dns.exception.Timeout, dns.resolver.NoNameservers):
            return MxResult(None, ())
        ranked = sorted(
            (
                (int(record.preference), str(record.exchange).rstrip(".").lower())
                for record in answers
            ),
            key=lambda item: item[0],
        )
        hosts = tuple(host for _, host in ranked if host)
        if not hosts:
            return MxResult(False, ())
        return MxResult(True, hosts)
