from roofleads.models import Lead, RunStats
from roofleads.normalize import canonical_origin, franchise_key, tidy, to_e164_us


def _score(lead: Lead) -> int:
    score = 0
    if lead.owner_name.strip():
        score += 2
    if to_e164_us(lead.phone):
        score += 1
    if canonical_origin(lead.website):
        score += 1
    if lead.city.strip():
        score += 1
    return score


def clean_leads(leads: list[Lead], *, stamp: str, stats: RunStats | None = None) -> list[Lead]:
    dropped_not_valid = 0
    dropped_missing = 0
    pool: list[Lead] = []
    for lead in leads:
        if lead.email_status != "valid":
            dropped_not_valid += 1
            continue
        if not tidy(lead.company_name) or not lead.email.strip():
            dropped_missing += 1
            continue
        normalized = Lead(
            company_name=tidy(lead.company_name),
            owner_name=tidy(lead.owner_name),
            email=lead.email.strip().lower(),
            website=canonical_origin(lead.website),
            phone=to_e164_us(lead.phone),
            city=tidy(lead.city),
            email_status="valid",
            source=lead.source,
            collected_at=stamp,
            place_id=lead.place_id,
            domain=franchise_key(lead.website, lead.email),
            seq=lead.seq,
            role_account=lead.role_account,
            local_reason=lead.local_reason,
            hunter_status=lead.hunter_status,
            confidence=lead.confidence,
        )
        pool.append(normalized)

    pool.sort(key=lambda lead: (-_score(lead), lead.seq, lead.email))
    seen_email: set[str] = set()
    seen_domain: set[str] = set()
    seen_phone: set[str] = set()
    kept: list[Lead] = []
    dupes_email = 0
    dupes_domain = 0
    dupes_phone = 0
    for lead in pool:
        if lead.email in seen_email:
            dupes_email += 1
            continue
        if lead.domain and lead.domain in seen_domain:
            dupes_domain += 1
            continue
        if lead.phone and lead.phone in seen_phone:
            dupes_phone += 1
            continue
        seen_email.add(lead.email)
        if lead.domain:
            seen_domain.add(lead.domain)
        if lead.phone:
            seen_phone.add(lead.phone)
        kept.append(lead)

    if stats is not None:
        stats.dropped_not_valid = dropped_not_valid
        stats.dropped_missing = dropped_missing
        stats.dupes_email = dupes_email
        stats.dupes_domain = dupes_domain
        stats.dupes_phone = dupes_phone
        stats.clean_kept = len(kept)
    return kept
