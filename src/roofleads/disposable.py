from pathlib import Path

from roofleads.errors import ConfigError
from roofleads.normalize import registered_domain


def parse_disposable_file(path: Path) -> set[str]:
    domains: set[str] = set()
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip().lower()
        if not line or line.startswith("#"):
            continue
        domains.add(line.rstrip("."))
    return domains


def load_builtin_disposable() -> set[str]:
    return parse_disposable_file(Path(__file__).with_name("disposable_domains.txt"))


def load_disposable(extra_file: str = "") -> set[str]:
    domains = load_builtin_disposable()
    if extra_file:
        path = Path(extra_file)
        if not path.exists():
            raise ConfigError(
                f"Disposable-domain file not found: {path}. "
                "Fix disposable_domains_file in roofleads.toml or leave it empty."
            )
        domains |= parse_disposable_file(path)
    return domains


def domain_is_disposable(domain: str, table: set[str]) -> bool:
    host = domain.strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return False
    if host in table:
        return True
    return registered_domain(host) in table
