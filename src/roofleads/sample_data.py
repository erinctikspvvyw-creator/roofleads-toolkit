from dataclasses import dataclass

from roofleads.config import DEFAULT_CITIES

DOMAIN_NO_MX = "nomx-roof.example"
DOMAIN_BAD_SYNTAX = "badsyntaxroof.example"
DOMAIN_INVALID = "invalidroof.example"
DOMAIN_ACCEPT_ALL = "acceptallroof.example"
DOMAIN_UNKNOWN = "unknownroof.example"
DOMAIN_WEBMAIL = "webmailroof.example"
DOMAIN_FRANCHISE = "lonestar-roof-pros.example"
DOMAIN_DISPOSABLE = "guerrillamail.com"
BAD_SYNTAX_EMAIL = "not-an-email"
CEDAR_EMAIL = "info@cedarpostroof.example"
CEDAR_PHONE = "(512) 555-0140"
CEDAR_OWNER = "Maria Santos"
CEDAR_NAME = "Cedar Post Roofing"

_AREA = {
    "Austin": "512",
    "Houston": "713",
    "Dallas": "214",
    "San Antonio": "210",
    "Fort Worth": "817",
    "El Paso": "915",
    "Arlington": "682",
    "Corpus Christi": "361",
    "Plano": "972",
    "Lubbock": "806",
    "Laredo": "956",
    "Irving": "469",
}

_STEMS = (
    "Cedar Post",
    "Mesa Shade",
    "Pecan Ridge",
    "Brazos Bend",
    "Live Oak",
    "Copper Flashing",
    "Blue Norther",
    "Caprock",
    "Guadalupe",
    "Trinity",
    "Palo Duro",
    "Caddo",
    "Neches",
    "Sabine",
    "Leon River",
    "Frio Canyon",
    "Comal Springs",
    "Pedernales",
    "Lavaca",
    "San Saba",
    "Llano",
    "Bosque",
    "Lampasas",
    "Concho",
    "Wichita Bend",
    "Pease River",
    "Clear Fork",
    "Elm Creek",
    "Post Oak",
    "Mesquite Flat",
    "Agave",
    "Yucca",
    "Huisache",
    "Retama",
    "Cibolo",
    "Blanco",
    "Onion Creek",
    "Shoal Creek",
    "Barton Creek",
)

_OWNERS = (
    "Maria Santos",
    "James Okonkwo",
    "Priya Shah",
    "Luis Ortega",
    "Helen Cho",
    "Andre Williams",
    "Fatima Rahman",
    "Chris Novak",
    "Elena Vasquez",
    "Robert Nguyen",
)


@dataclass
class SampleCompany:
    company_name: str
    city: str
    phone: str
    website: str
    email: str
    owner_name: str
    owner_position: str
    email_type: str
    confidence: int
    verify_status: str
    place_id: str
    state: str = "Texas"
    mx: bool = True


def _row(city: str, number: int) -> SampleCompany:
    slug = f"roof-{number:03d}"
    return SampleCompany(
        company_name=f"{_STEMS[(number - 1) % len(_STEMS)]} Roofing",
        city=city,
        phone=f"({_AREA[city]}) 555-{1000 + number:04d}",
        website=f"https://www.{slug}.example/contact",
        email=f"info@{slug}.example",
        owner_name=_OWNERS[(number - 1) % len(_OWNERS)],
        owner_position="Owner",
        email_type="generic",
        confidence=88,
        verify_status="valid",
        place_id=f"plc-{number:04d}",
    )


def _set_domain(row: SampleCompany, domain: str, *, status: str, email: str | None = None, email_type: str = "generic") -> None:
    row.website = f"https://www.{domain}/contact"
    row.email = email if email is not None else f"info@{domain}"
    row.email_type = email_type
    row.verify_status = status
    row.place_id = f"plc-{domain.split('.')[0]}"


def build_sample_companies() -> list[SampleCompany]:
    """Bundled fictional companies on the .example domain. Not real businesses."""
    rows: list[SampleCompany] = []
    number = 0
    for city in DEFAULT_CITIES:
        for _ in range(10):
            number += 1
            rows.append(_row(city, number))
    by_city: dict[str, list[SampleCompany]] = {}
    for row in rows:
        by_city.setdefault(row.city, []).append(row)

    austin = by_city["Austin"]
    austin[0].company_name = CEDAR_NAME
    austin[0].website = "https://www.cedarpostroof.example/contact"
    austin[0].email = CEDAR_EMAIL
    austin[0].phone = CEDAR_PHONE
    austin[0].owner_name = CEDAR_OWNER
    austin[0].place_id = "plc-cedar-post"

    austin[8].company_name = "Lonestar Roof Pros"
    austin[8].website = f"https://www.{DOMAIN_FRANCHISE}"
    austin[8].email = f"info@{DOMAIN_FRANCHISE}"
    austin[8].owner_name = "James Okonkwo"
    austin[8].place_id = "plc-lonestar"
    austin[8].verify_status = "valid"

    _set_domain(austin[9], DOMAIN_INVALID, status="invalid")
    austin[9].company_name = "Red Flashing Roofing"

    houston = by_city["Houston"]
    houston[0].company_name = "Lonestar Roof Pros Houston"
    houston[0].website = f"https://{DOMAIN_FRANCHISE}/houston"
    houston[0].email = f"houston@{DOMAIN_FRANCHISE}"
    houston[0].email_type = "personal"
    houston[0].owner_name = "James Okonkwo"
    houston[0].place_id = "plc-lonestar-houston"
    houston[0].verify_status = "valid"

    houston[1].company_name = "Bayou Match Roofing"
    houston[1].website = "https://www.bayoumatchroof.example"
    houston[1].email = "info@bayoumatchroof.example"
    houston[1].phone = CEDAR_PHONE
    houston[1].place_id = "plc-bayou-match"
    houston[1].verify_status = "valid"

    _set_domain(houston[2], DOMAIN_ACCEPT_ALL, status="accept_all")
    houston[2].company_name = "Accept All Roofing"
    _set_domain(houston[3], DOMAIN_UNKNOWN, status="unknown")
    houston[3].company_name = "Unknown Mail Roofing"

    dallas = by_city["Dallas"]
    dallas[0].company_name = "Hill, Mesa & Co. Roofing"
    dallas[0].place_id = "plc-hill-mesa"
    _set_domain(dallas[9], DOMAIN_WEBMAIL, status="webmail")
    dallas[9].company_name = "Webmail Roofing"

    by_city["San Antonio"][0].company_name = "Peña Roofing"
    by_city["San Antonio"][0].place_id = "plc-pena"

    rows.extend(
        [
            SampleCompany(
                company_name="",
                city="Austin",
                phone="(512) 555-0191",
                website="https://www.blankname-roof.example",
                email="info@blankname-roof.example",
                owner_name="Pat Blank",
                owner_position="Owner",
                email_type="generic",
                confidence=80,
                verify_status="valid",
                place_id="plc-blank-name",
            ),
            SampleCompany(
                company_name="No Site Roofing",
                city="Austin",
                phone="(512) 555-0192",
                website="",
                email="",
                owner_name="",
                owner_position="",
                email_type="",
                confidence=0,
                verify_status="valid",
                place_id="plc-no-site",
            ),
            SampleCompany(
                company_name="Disposable Host Roofing",
                city="Austin",
                phone="(512) 555-0193",
                website=f"https://crew.{DOMAIN_DISPOSABLE}/roof",
                email=f"info@{DOMAIN_DISPOSABLE}",
                owner_name="Disposable Owner",
                owner_position="Owner",
                email_type="generic",
                confidence=80,
                verify_status="disposable",
                place_id="plc-disposable",
            ),
            SampleCompany(
                company_name="Social Only Roofing",
                city="Austin",
                phone="(512) 555-0194",
                website="https://www.facebook.com/someroofer",
                email="info@facebook.com",
                owner_name="Social Owner",
                owner_position="Owner",
                email_type="generic",
                confidence=80,
                verify_status="valid",
                place_id="plc-facebook",
            ),
            SampleCompany(
                company_name="Sooner Roofing",
                city="Austin",
                phone="(512) 555-0195",
                website="https://www.oklahomaroofer.example",
                email="info@oklahomaroofer.example",
                owner_name="Casey Sooner",
                owner_position="Owner",
                email_type="generic",
                confidence=80,
                verify_status="valid",
                place_id="plc-oklahoma",
                state="Oklahoma",
            ),
            SampleCompany(
                company_name="Bad Syntax Roofing",
                city="Austin",
                phone="(512) 555-0196",
                website=f"https://www.{DOMAIN_BAD_SYNTAX}",
                email=BAD_SYNTAX_EMAIL,
                owner_name="Syntax Owner",
                owner_position="Owner",
                email_type="generic",
                confidence=80,
                verify_status="valid",
                place_id="plc-bad-syntax",
            ),
            SampleCompany(
                company_name="No MX Roofing",
                city="Austin",
                phone="(512) 555-0197",
                website=f"https://www.{DOMAIN_NO_MX}",
                email=f"info@{DOMAIN_NO_MX}",
                owner_name="Mx Owner",
                owner_position="Owner",
                email_type="generic",
                confidence=80,
                verify_status="valid",
                place_id="plc-no-mx",
                mx=False,
            ),
        ]
    )
    return rows
