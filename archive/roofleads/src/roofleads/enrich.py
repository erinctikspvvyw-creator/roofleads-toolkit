from dataclasses import dataclass

from roofleads.normalize import email_on_domain, is_owner_position, is_role_address, tidy


@dataclass(frozen=True)
class Person:
    value: str
    type: str
    confidence: int | None
    first_name: str
    last_name: str
    position: str


@dataclass(frozen=True)
class Choice:
    email: str
    owner_name: str
    confidence: int | None
    email_type: str
    position: str


def people_from_payload(payload: object) -> list[Person]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}
    rows = data.get("emails") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    people: list[Person] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_confidence = item.get("confidence")
        confidence = None if raw_confidence is None or raw_confidence == "" else int(raw_confidence)
        people.append(
            Person(
                value=str(item.get("value") or "").strip(),
                type=str(item.get("type") or "").strip().lower(),
                confidence=confidence,
                first_name=tidy(str(item.get("first_name") or "")),
                last_name=tidy(str(item.get("last_name") or "")),
                position=tidy(str(item.get("position") or "")),
            )
        )
    return people


def _confidence_ok(confidence: int | None, minimum: int) -> bool:
    if confidence is None:
        return True
    return confidence >= minimum


def _public_name(person: Person) -> str:
    if not person.first_name or not person.last_name:
        return ""
    if is_role_address(person.first_name):
        return ""
    return tidy(f"{person.first_name} {person.last_name}")


def choose_owner(people: list[Person], *, company_domain: str, min_confidence: int) -> str:
    named = [
        person
        for person in people
        if _confidence_ok(person.confidence, min_confidence)
        and is_owner_position(person.position)
        and _public_name(person)
        and email_on_domain(person.value, company_domain)
        and "@" in person.value
    ]
    if not named:
        return ""
    best = sorted(named, key=lambda person: (-(person.confidence or 0), person.value.lower()))[0]
    return _public_name(best)


def pick_contact(
    people: list[Person],
    *,
    company_domain: str,
    min_confidence: int,
    prefer_role: bool,
) -> Choice | None:
    eligible: list[Person] = []
    for person in people:
        if not person.value or not _confidence_ok(person.confidence, min_confidence):
            continue
        if not email_on_domain(person.value, company_domain):
            continue
        eligible.append(person)
    if not eligible:
        return None

    def sort_key(person: Person) -> tuple[int, int, str]:
        role = is_role_address(person.value) or person.type == "generic"
        role_rank = 0 if (role if prefer_role else not role) else 1
        return (role_rank, -(person.confidence or 0), person.value.lower())

    best = sorted(eligible, key=sort_key)[0]
    return Choice(
        email=best.value.strip(),
        owner_name=choose_owner(people, company_domain=company_domain, min_confidence=min_confidence),
        confidence=best.confidence,
        email_type="generic" if is_role_address(best.value) or best.type == "generic" else best.type or "personal",
        position=best.position,
    )
