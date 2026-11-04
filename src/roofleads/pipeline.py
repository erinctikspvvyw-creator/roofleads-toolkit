import time
from dataclasses import dataclass
from pathlib import Path

from roofleads.cache import stable_hash
from roofleads.clean import clean_leads
from roofleads.discover import (
    actor_input,
    actual_run_micro,
    estimate_run_micro,
    fetch_dataset_items,
    place_to_lead,
    source_label,
    start_actor_run,
    wait_for_run,
)
from roofleads.disposable import domain_is_disposable
from roofleads.enrich import people_from_payload, pick_contact
from roofleads.errors import ApiError
from roofleads.export import build_report, write_csv, write_jsonl, write_reports
from roofleads.models import Lead, lead_from_record, utc_stamp
from roofleads.normalize import company_domain, website_is_shared_host
from roofleads.runtime import Runtime
from roofleads.verify import local_check, status_from_verdict, verdict_from_payload


@dataclass
class PipelineResult:
    delivered: int
    csv_path: Path
    qa_json_path: Path
    qa_text_path: Path
    stopped_reason: str | None
    error: str | None
    report: dict[str, object]


def _identity(lead: Lead) -> str:
    if lead.place_id:
        return f"id:{lead.place_id}"
    return f"row:{lead.company_name.lower()}|{lead.city.lower()}|{lead.website.lower()}"


def _take_new(leads: list[Lead], seen: set[str], runtime: Runtime) -> list[Lead]:
    fresh: list[Lead] = []
    for lead in leads:
        key = _identity(lead)
        if key in seen:
            runtime.stats.discover_duplicate_places += 1
            continue
        seen.add(key)
        fresh.append(lead)
    runtime.stats.discover_places += len(fresh)
    return fresh


def discover_city(runtime: Runtime, city: str, seen: set[str]) -> list[Lead]:
    settings = runtime.settings
    body = actor_input(settings, city)
    key = stable_hash({"actor": settings.actor_id, "input": body})
    cached = runtime.cache.get_discover(key)
    if cached:
        runtime.stats.discover_cached_runs += 1
        runtime.stats.discover_skipped_no_name += int(cached.get("skipped_no_name") or 0)
        runtime.stats.discover_skipped_outside_area += int(cached.get("skipped_outside_area") or 0)
        leads = [_lead_from_cached(item) for item in cached.get("items") or []]
        runtime.log.info(
            "city search served from cache",
            extra={"fields": {"event": "discover.city", "city": city, "kept": len(leads), "cached": True}},
        )
        return _take_new(leads, seen, runtime)

    term_count = len(body["searchStringsArray"]) if isinstance(body["searchStringsArray"], list) else 1
    estimate = estimate_run_micro(settings, int(term_count))
    if not runtime.budget.can_afford_apify(estimate):
        runtime.budget.stop_for_apify(estimate, f"an Apify search for {city}, Texas")
        runtime.log.info(
            runtime.budget.stopped_reason or "apify budget stop",
            extra={"fields": {"event": "budget.stop", "city": city}},
        )
        return []

    started = False
    try:
        run = start_actor_run(runtime.http, settings, runtime.token, body)
        started = True
        run_id = str(run.get("id") or "")
        dataset_id = str(run.get("defaultDatasetId") or "")
        if str(run.get("status") or "") != "SUCCEEDED":
            finished = wait_for_run(
                runtime.http,
                run_id,
                runtime.token,
                timeout_seconds=settings.apify_run_timeout_seconds,
                poll_seconds=settings.apify_poll_seconds,
                monotonic=time.monotonic,
                sleeper=time.sleep,
            )
            dataset_id = str(finished.get("defaultDatasetId") or dataset_id)
        raw_items = fetch_dataset_items(runtime.http, dataset_id, runtime.token)
    except ApiError:
        if started:
            runtime.budget.charge_apify(estimate)
            runtime.cache.save(runtime.budget)
        raise

    kept: list[Lead] = []
    skipped_no_name = 0
    skipped_outside = 0
    for item in raw_items:
        lead, reason = place_to_lead(item, fallback_city=city, source=source_label(settings))
        if reason == "no_name":
            skipped_no_name += 1
            continue
        if reason == "outside_area":
            skipped_outside += 1
            continue
        if lead is not None:
            kept.append(lead)
    runtime.stats.discover_runs += 1
    runtime.stats.discover_skipped_no_name += skipped_no_name
    runtime.stats.discover_skipped_outside_area += skipped_outside
    runtime.cache.set_discover(
        key,
        {
            "city": city,
            "items": [lead.to_record() for lead in kept],
            "skipped_no_name": skipped_no_name,
            "skipped_outside_area": skipped_outside,
            "raw_result_count": len(raw_items),
        },
    )
    cost = actual_run_micro(settings, len(raw_items))
    projected = runtime.budget.lifetime_apify_micro + cost
    runtime.budget.charge_apify(cost)
    runtime.cache.save(runtime.budget)
    if projected > runtime.budget.max_apify_micro and not runtime.budget.stopped_reason:
        runtime.budget.stopped_reason = (
            f"Apify returned more places for {city} than the budget had reserved. "
            "Places already downloaded will still be checked. Further city searches are stopped. "
            "Raise --max-apify-usd to continue."
        )
    runtime.log.info(
        "city search finished",
        extra={
            "fields": {
                "event": "discover.city",
                "city": city,
                "kept": len(kept),
                "cached": False,
                "apify_micro_usd": cost,
            }
        },
    )
    return _take_new(kept, seen, runtime)


def _lead_from_cached(item: object) -> Lead:
    if not isinstance(item, dict):
        return Lead()
    return lead_from_record(item)


def _apply_contact(lead: Lead, domain: str, record: dict[str, object]) -> None:
    lead.domain = domain
    lead.email = str(record.get("email") or "").strip().lower()
    lead.owner_name = str(record.get("owner_name") or "")
    confidence = record.get("confidence")
    lead.confidence = None if confidence is None or confidence == "" else int(str(confidence))


def _tally_email(runtime: Runtime, lead: Lead) -> None:
    if lead.email:
        runtime.stats.enrich_with_email += 1
    else:
        runtime.stats.enrich_no_email += 1


def enrich_lead(runtime: Runtime, lead: Lead) -> Lead | None:
    runtime.stats.enrich_attempted += 1
    if not lead.website.strip():
        runtime.stats.enrich_skipped_no_domain += 1
        runtime.stats.enrich_no_email += 1
        return lead
    if website_is_shared_host(lead.website):
        runtime.stats.enrich_skipped_shared_host += 1
        runtime.stats.enrich_no_email += 1
        return lead
    domain = company_domain(lead.website)
    if domain and domain_is_disposable(domain, runtime.disposable):
        runtime.stats.enrich_skipped_disposable_domain += 1
        runtime.stats.enrich_no_email += 1
        return lead
    if not domain:
        runtime.stats.enrich_skipped_no_domain += 1
        runtime.stats.enrich_no_email += 1
        return lead

    cached = runtime.cache.get_domain(domain)
    search_cost = runtime.settings.hunter_credits_per_domain_search
    if cached:
        runtime.stats.enrich_cache_hits += 1
        runtime.stats.credits_saved_by_cache += search_cost
        _apply_contact(lead, domain, cached)
        _tally_email(runtime, lead)
        return lead
    if not runtime.budget.can_afford_credits(search_cost):
        runtime.budget.stop_for_credits(search_cost, f"a Hunter domain search for {domain}")
        runtime.log.info(
            runtime.budget.stopped_reason or "hunter budget stop",
            extra={"fields": {"event": "budget.stop", "domain": domain}},
        )
        return None

    params = {"domain": domain, "limit": "10"}
    if runtime.hunter_key:
        params["api_key"] = runtime.hunter_key
    payload = runtime.http.request_json(
        "GET",
        "https://api.hunter.io/v2/domain-search",
        params=params,
        group="hunter",
    )
    choice = pick_contact(
        people_from_payload(payload),
        company_domain=domain,
        min_confidence=runtime.settings.min_confidence,
        prefer_role=runtime.settings.prefer_role_emails,
    )
    record: dict[str, object] = {
        "email": choice.email if choice else "",
        "owner_name": choice.owner_name if choice else "",
        "confidence": None if choice is None else choice.confidence,
        "email_type": "" if choice is None else choice.email_type,
        "position": "" if choice is None else choice.position,
    }
    runtime.cache.set_domain(domain, record)
    runtime.budget.charge_credits(search_cost)
    runtime.cache.save(runtime.budget)
    runtime.stats.enrich_api_calls += 1
    runtime.stats.enrich_credits += search_cost
    _apply_contact(lead, domain, record)
    _tally_email(runtime, lead)
    runtime.log.debug(
        "domain search finished",
        extra={"fields": {"event": "enrich.search", "domain": domain, "found": bool(lead.email)}},
    )
    return lead


def verify_lead(runtime: Runtime, lead: Lead) -> Lead | None:
    if not lead.email:
        return lead
    lead.email = lead.email.strip().lower()
    runtime.stats.verify_attempted += 1
    local = local_check(lead.email, runtime.mx, runtime.disposable)
    lead.role_account = local.role_account
    if local.role_account:
        runtime.stats.verify_role_flagged += 1
    if not local.passed:
        lead.email_status = local.status_if_failed
        lead.local_reason = local.reason
        if local.status_if_failed == "unknown":
            runtime.stats.verify_local_unknown += 1
        else:
            runtime.stats.verify_local_invalid += 1
        runtime.stats.bump_status(lead.email_status)
        return lead
    if local.role_account and runtime.settings.reject_role_accounts:
        lead.email_status = "risky"
        lead.local_reason = "role_account"
        runtime.stats.verify_skipped_role_policy += 1
        runtime.stats.bump_status("risky")
        return lead

    verify_cost = runtime.settings.hunter_credits_per_verification
    cached = runtime.cache.get_email(lead.email)
    if cached:
        runtime.stats.verify_cache_hits += 1
        runtime.stats.credits_saved_by_cache += verify_cost
        lead.email_status = str(cached.get("email_status") or "unknown")
        lead.hunter_status = str(cached.get("hunter_status") or "")
        lead.local_reason = str(cached.get("local_reason") or "")
        runtime.stats.bump_status(lead.email_status)
        return lead

    if runtime.smtp_probe is not None and local.mx_hosts:
        probed = runtime.smtp_probe(lead.email, local.mx_hosts[0])
        if probed == "rejected":
            lead.email_status = "invalid"
            lead.local_reason = "smtp_rejected"
            runtime.stats.verify_smtp_rejected += 1
            runtime.stats.bump_status("invalid")
            return lead

    if not runtime.budget.can_afford_credits(verify_cost):
        runtime.budget.stop_for_credits(verify_cost, f"a Hunter verification for {lead.domain or 'a company email'}")
        runtime.log.info(
            runtime.budget.stopped_reason or "hunter budget stop",
            extra={"fields": {"event": "budget.stop", "domain": lead.domain}},
        )
        return None

    params = {"email": lead.email}
    if runtime.hunter_key:
        params["api_key"] = runtime.hunter_key
    payload = runtime.http.request_json(
        "GET",
        "https://api.hunter.io/v2/email-verifier",
        params=params,
        group="hunter",
    )
    verdict = verdict_from_payload(payload)
    lead.hunter_status = verdict
    lead.email_status = status_from_verdict(verdict)
    lead.local_reason = ""
    runtime.cache.set_email(
        lead.email,
        {
            "email_status": lead.email_status,
            "hunter_status": verdict,
            "role_account": lead.role_account,
            "local_reason": "",
        },
    )
    runtime.budget.charge_credits(verify_cost)
    runtime.cache.save(runtime.budget)
    runtime.stats.verify_api_calls += 1
    runtime.stats.verify_credits += verify_cost
    runtime.stats.bump_status(lead.email_status)
    runtime.log.debug(
        "email verification finished",
        extra={"fields": {"event": "verify.email", "domain": lead.domain, "status": lead.email_status}},
    )
    return lead


def _deliverable_count(verified: list[Lead], runtime: Runtime) -> int:
    return len(clean_leads(verified, stamp=utc_stamp(runtime.clock)))


def run_pipeline(runtime: Runtime, output_dir: Path, target_rows: int) -> PipelineResult:
    seen: set[str] = set()
    discovered: list[Lead] = []
    enriched: list[Lead] = []
    verified: list[Lead] = []
    pending: list[Lead] = []
    cities = iter(runtime.settings.cities)
    seq = 1
    error: str | None = None
    try:
        while True:
            if _deliverable_count(verified, runtime) >= target_rows:
                break
            if pending:
                lead = pending.pop(0)
                contact = enrich_lead(runtime, lead)
                if contact is None:
                    break
                enriched.append(contact)
                if contact.email:
                    checked = verify_lead(runtime, contact)
                    if checked is None:
                        break
                    verified.append(checked)
                if not pending:
                    ready = _deliverable_count(verified, runtime)
                    runtime.say(f"Deliverable emails so far: {min(ready, target_rows)}")
                continue
            if runtime.budget.stopped_reason:
                break
            try:
                city = next(cities)
            except StopIteration:
                runtime.stats.cities_exhausted = True
                break
            runtime.say(f"Discovering roofing companies in {city}, Texas...")
            batch = discover_city(runtime, city, seen)
            for lead in batch:
                lead.seq = seq
                seq += 1
                discovered.append(lead)
                pending.append(lead)
            runtime.say(f"{city}: found {len(batch)} companies")
            if not batch and runtime.budget.stopped_reason:
                break
    except ApiError as exc:
        error = str(exc)
        runtime.log.error(error, extra={"fields": {"event": "pipeline.error"}})

    stamp = utc_stamp(runtime.clock)
    deliverable = clean_leads(verified, stamp=stamp, stats=runtime.stats)
    chosen = deliverable[:target_rows]
    chosen.sort(key=lambda lead: (lead.city.lower(), lead.company_name.lower(), lead.email))
    runtime.stats.delivered = len(chosen)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "discovered.jsonl", [lead.to_record() for lead in discovered])
    write_jsonl(output_dir / "enriched.jsonl", [lead.to_record() for lead in enriched])
    write_jsonl(output_dir / "verified.jsonl", [lead.to_record() for lead in verified])
    write_jsonl(output_dir / "cleaned.jsonl", [lead.to_record() for lead in chosen])
    csv_path = output_dir / "leads.csv"
    write_csv(csv_path, chosen)
    report = build_report(
        stats=runtime.stats,
        budget=runtime.budget,
        settings=runtime.settings,
        mode=runtime.mode,
        target_rows=target_rows,
        delivered=chosen,
        generated_at=stamp,
        output_dir=output_dir,
    )
    qa_json, qa_text = write_reports(output_dir, report)
    runtime.log.info(
        "pipeline finished",
        extra={"fields": {"event": "pipeline.done", "delivered": len(chosen), "target": target_rows}},
    )
    return PipelineResult(
        delivered=len(chosen),
        csv_path=csv_path,
        qa_json_path=qa_json,
        qa_text_path=qa_text,
        stopped_reason=runtime.budget.stopped_reason,
        error=error,
        report=report,
    )


def discover_all(runtime: Runtime) -> list[Lead]:
    seen: set[str] = set()
    found: list[Lead] = []
    seq = 1
    for city in runtime.settings.cities:
        if runtime.budget.stopped_reason:
            break
        runtime.say(f"Discovering roofing companies in {city}, Texas...")
        batch = discover_city(runtime, city, seen)
        runtime.say(f"{city}: found {len(batch)} companies")
        for lead in batch:
            lead.seq = seq
            seq += 1
            found.append(lead)
        if not batch and runtime.budget.stopped_reason:
            break
    return found
