import re
import unicodedata
from urllib.parse import urlparse

ROLE_LOCAL_PARTS = frozenset(
    {
        "info",
        "contact",
        "contacts",
        "sales",
        "support",
        "admin",
        "office",
        "hello",
        "enquiries",
        "inquiries",
        "enquiry",
        "inquiry",
        "billing",
        "accounts",
        "noreply",
        "no-reply",
        "webmaster",
        "postmaster",
        "marketing",
        "jobs",
        "careers",
        "hr",
        "team",
        "service",
        "services",
        "estimating",
        "estimate",
        "mail",
        "email",
        "general",
        "reception",
        "frontdesk",
        "customerservice",
        "customer-service",
        "customersupport",
    }
)

# Directory and social hosts are not a roofing company's own mail domain.
SHARED_REGISTRABLE = frozenset(
    {
        "facebook.com",
        "fb.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "linkedin.com",
        "yelp.com",
        "yellowpages.com",
        "bbb.org",
        "youtube.com",
        "tiktok.com",
        "nextdoor.com",
        "angi.com",
        "angieslist.com",
        "homeadvisor.com",
        "thumbtack.com",
        "mapquest.com",
        "google.com",
        "goo.gl",
        "linktr.ee",
        "bit.ly",
        "business.site",
    }
)

# Website builders. Searching the parent domain would bill Hunter for a host
# the contractor does not own.
PLATFORM_REGISTRABLE = frozenset(
    {
        "wixsite.com",
        "wix.com",
        "square.site",
        "godaddysites.com",
        "myshopify.com",
        "weebly.com",
        "carrd.co",
        "jimdosite.com",
        "webflow.io",
        "notion.site",
    }
)

_MULTI_PART_SUFFIXES = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "net.au",
        "org.au",
        "co.nz",
        "com.br",
        "com.mx",
        "co.jp",
        "co.za",
        "com.tr",
    }
)

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_OWNER_WORDS = frozenset(
    {"owner", "founder", "cofounder", "president", "ceo", "principal", "proprietor"}
)
_OWNER_PHRASES = (
    "co founder",
    "chief executive",
    "managing partner",
    "general manager",
)


def tidy(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text or "")
    return re.sub(r"\s+", " ", normalized).strip()


def registered_domain(host: str) -> str:
    host = host.strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return host
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _MULTI_PART_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def host_from_website(website: str) -> str:
    text = (website or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    host = (urlparse(text).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def canonical_origin(website: str) -> str:
    host = host_from_website(website)
    if not host:
        return ""
    return f"https://{host}"


def company_domain(website: str) -> str:
    """Registrable domain worth a Hunter search, or empty when there is none."""
    host = host_from_website(website)
    if not host or "." not in host:
        return ""
    registered = registered_domain(host)
    if registered in SHARED_REGISTRABLE or registered in PLATFORM_REGISTRABLE:
        return ""
    return registered


def website_is_shared_host(website: str) -> bool:
    host = host_from_website(website)
    if not host:
        return False
    registered = registered_domain(host)
    return registered in SHARED_REGISTRABLE or registered in PLATFORM_REGISTRABLE


def franchise_key(website: str, email: str) -> str:
    host = host_from_website(website)
    if host:
        registered = registered_domain(host)
        if registered in SHARED_REGISTRABLE or registered in PLATFORM_REGISTRABLE:
            return ""
        return registered
    if "@" in email:
        return registered_domain(email.rsplit("@", 1)[1])
    return ""


def to_e164_us(phone: str) -> str:
    if not phone:
        return ""
    without_extension = re.split(r"(?:ext\.?|extension|x)\s*\d+\s*$", phone, maxsplit=1, flags=re.I)[0]
    digits = re.sub(r"\D", "", without_extension)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return ""
    if digits[0] in "01" or digits[3] in "01":
        return ""
    return "+1" + digits


def syntax_ok(email: str) -> bool:
    if not email or len(email) > 254 or email.count("@") != 1:
        return False
    if not _EMAIL_RE.match(email):
        return False
    local, domain = email.rsplit("@", 1)
    if ".." in email or local.startswith(".") or local.endswith("."):
        return False
    if domain.startswith(".") or domain.endswith("."):
        return False
    return True


def email_local_part(email: str) -> str:
    local = email.split("@", 1)[0].lower()
    return local.split("+", 1)[0]


def is_role_address(email: str) -> bool:
    if "@" not in email:
        return False
    local = email_local_part(email)
    if local in ROLE_LOCAL_PARTS:
        return True
    head = re.split(r"[._-]", local, maxsplit=1)[0]
    return head in ROLE_LOCAL_PARTS


def email_on_domain(email: str, domain: str) -> bool:
    if "@" not in email:
        return True
    host = email.rsplit("@", 1)[1].lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host == domain or registered_domain(host) == domain


def is_owner_position(position: str) -> bool:
    text = re.sub(r"[^a-z0-9]+", " ", (position or "").lower()).strip()
    if not text:
        return False
    words = set(text.split())
    if words & _OWNER_WORDS:
        return True
    return any(phrase in text for phrase in _OWNER_PHRASES)
