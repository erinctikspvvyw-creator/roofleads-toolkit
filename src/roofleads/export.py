import csv
import json
from decimal import Decimal
from pathlib import Path

from roofleads.budget import Budget, micro_to_money
from roofleads.config import Settings
from roofleads.errors import ConfigError, ExportError
from roofleads.models import CSV_COLUMNS, Lead, RunStats


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise ConfigError(
            f"Input file not found: {path}. Run the earlier stage first, or pass the right --output-dir."
        )
    rows: list[dict[str, object]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Could not read {path} line {line_no}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ConfigError(f"Could not read {path} line {line_no}: expected an object.")
        rows.append(parsed)
    return rows


def write_csv(path: Path, leads: list[Lead]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            if lead.email_status != "valid":
                raise ExportError(
                    "Refusing to write a row whose email_status is not valid. "
                    "Only checked, deliverable emails belong in the delivery file."
                )
            if not lead.company_name or not lead.email:
                raise ExportError("Refusing to write a row missing company_name or email.")
            writer.writerow(lead.to_public_row())


def _money_times_credits(credits: int, usd_per_credit: Decimal) -> str:
    micro = int((Decimal(credits) * usd_per_credit * Decimal(1_000_000)).to_integral_value())
    return micro_to_money(micro)


def build_report(
    *,
    stats: RunStats,
    budget: Budget,
    settings: Settings,
    mode: str,
    target_rows: int,
    delivered: list[Lead],
    generated_at: str,
    output_dir: Path,
) -> dict[str, object]:
    delivered_rows = len(delivered)
    valid_rows = sum(1 for lead in delivered if lead.email_status == "valid")
    rate = (valid_rows / delivered_rows) if delivered_rows else 0.0
    hunter_usd = _money_times_credits(budget.run_hunter, settings.hunter_usd_per_credit)
    apify_usd = micro_to_money(budget.run_apify_micro)
    total_micro = budget.run_apify_micro + int(
        (Decimal(budget.run_hunter) * settings.hunter_usd_per_credit * Decimal(1_000_000)).to_integral_value()
    )
    total_usd = micro_to_money(total_micro)
    if delivered_rows:
        per_row = micro_to_money(int(Decimal(total_micro) / Decimal(delivered_rows)))
    else:
        per_row = "n/a"
    warnings: list[str] = []
    if budget.stopped_reason:
        warnings.append(budget.stopped_reason)
    if stats.cities_exhausted and delivered_rows < target_rows:
        warnings.append(
            "The city list ran out before the row target was met. "
            "Add cities under [discover] in roofleads.toml and run the same command again."
        )
    if delivered_rows < target_rows and not warnings:
        warnings.append(
            f"Delivered {delivered_rows} of {target_rows} requested rows. See the stage counts for what was dropped."
        )
    report: dict[str, object] = {
        "mode": mode,
        "generated_at": generated_at,
        "target_rows": target_rows,
        "delivered_rows": delivered_rows,
        "delivered_valid_rate": f"{rate:.4f}",
        "meets_quality_target": delivered_rows > 0 and rate >= 0.9,
        "quality_target": "0.90",
        "estimated_total_usd": total_usd,
        "cost_per_delivered_row_usd": per_row,
        "stopped_reason": budget.stopped_reason,
        "warnings": warnings,
        "csv_columns": list(CSV_COLUMNS),
        "output": {
            "csv": str(output_dir / "leads.csv"),
            "qa_json": str(output_dir / "qa_report.json"),
            "qa_text": str(output_dir / "qa_report.txt"),
        },
        "budget": {
            "max_hunter_credits": budget.max_credits,
            "max_apify_usd": micro_to_money(budget.max_apify_micro),
            "this_run": {
                "hunter_credits": budget.run_hunter,
                "hunter_estimated_usd": hunter_usd,
                "apify_usd": apify_usd,
                "apify_micro_usd": budget.run_apify_micro,
            },
            "lifetime": {
                "hunter_credits": budget.lifetime_hunter,
                "apify_usd": micro_to_money(budget.lifetime_apify_micro),
                "apify_micro_usd": budget.lifetime_apify_micro,
            },
            "hunter_credits_saved_by_cache": stats.credits_saved_by_cache,
        },
        "rate_card": {
            "hunter_usd_per_credit": format(settings.hunter_usd_per_credit, "f"),
            "hunter_credits_per_domain_search": settings.hunter_credits_per_domain_search,
            "hunter_credits_per_verification": settings.hunter_credits_per_verification,
            "apify_usd_per_place": format(settings.apify_usd_per_place, "f"),
            "apify_usd_per_filter": format(settings.apify_usd_per_filter, "f"),
            "apify_usd_per_start": format(settings.apify_usd_per_start, "f"),
            "apify_filters_per_place": int(settings.website_filter not in {"", "allPlaces"})
            + int(settings.skip_closed_places),
            "note": "Planning estimates from the rate card in roofleads.toml. Confirm the invoice in Apify and Hunter.",
        },
        "formulas": {
            "estimated_total_usd": "this_run.apify_usd + this_run.hunter_credits * hunter_usd_per_credit",
            "cost_per_delivered_row_usd": "estimated_total_usd / delivered_rows",
            "delivered_valid_rate": "delivered rows with email_status=valid / delivered_rows",
        },
        "stages": {
            "discover": {
                "runs": stats.discover_runs,
                "cached_runs": stats.discover_cached_runs,
                "places_kept": stats.discover_places,
                "skipped_no_name": stats.discover_skipped_no_name,
                "skipped_outside_area": stats.discover_skipped_outside_area,
                "duplicate_places": stats.discover_duplicate_places,
            },
            "enrich": {
                "attempted": stats.enrich_attempted,
                "with_email": stats.enrich_with_email,
                "no_email": stats.enrich_no_email,
                "skipped_no_domain": stats.enrich_skipped_no_domain,
                "skipped_shared_host": stats.enrich_skipped_shared_host,
                "skipped_disposable_domain": stats.enrich_skipped_disposable_domain,
                "cache_hits": stats.enrich_cache_hits,
                "api_calls": stats.enrich_api_calls,
                "credits": stats.enrich_credits,
            },
            "verify": {
                "attempted": stats.verify_attempted,
                "local_invalid": stats.verify_local_invalid,
                "local_unknown": stats.verify_local_unknown,
                "cache_hits": stats.verify_cache_hits,
                "api_calls": stats.verify_api_calls,
                "credits": stats.verify_credits,
                "role_flagged": stats.verify_role_flagged,
                "skipped_role_policy": stats.verify_skipped_role_policy,
                "smtp_rejected": stats.verify_smtp_rejected,
                "by_status": dict(stats.status_counts),
            },
            "clean": {
                "dropped_not_valid": stats.dropped_not_valid,
                "dropped_missing": stats.dropped_missing,
                "dupes_email": stats.dupes_email,
                "dupes_domain": stats.dupes_domain,
                "dupes_phone": stats.dupes_phone,
                "kept": stats.clean_kept,
            },
            "export": {"rows": delivered_rows},
        },
    }
    return report


def _count(value: object, singular: str, plural: str | None = None) -> str:
    number = int(str(value))
    word = singular if number == 1 else (plural or f"{singular}s")
    return f"{number} {word}"


def render_text_report(report: dict[str, object]) -> str:
    budget = report["budget"]
    assert isinstance(budget, dict)
    this_run = budget["this_run"]
    lifetime = budget["lifetime"]
    stages = report["stages"]
    assert isinstance(this_run, dict) and isinstance(lifetime, dict) and isinstance(stages, dict)
    discover = stages["discover"]
    enrich = stages["enrich"]
    verify = stages["verify"]
    clean = stages["clean"]
    assert isinstance(discover, dict) and isinstance(enrich, dict)
    assert isinstance(verify, dict) and isinstance(clean, dict)
    by_status = verify["by_status"]
    assert isinstance(by_status, dict)
    rate = float(str(report["delivered_valid_rate"])) * 100
    per_row = report["cost_per_delivered_row_usd"] or "n/a"
    lines = [
        "Roofing lead list — QA report",
        f"Mode: {report['mode']}",
        f"Generated: {report['generated_at']}",
        "",
        f"Delivered {report['delivered_rows']} of {report['target_rows']} requested rows.",
        f"Valid-email rate among delivered rows: {rate:.1f}%.",
        "The 90% deliverable target is met."
        if report["meets_quality_target"]
        else "The 90% deliverable target is not met.",
        "",
        "Cost estimate for this run (check the Apify and Hunter invoices for the real charge)",
        f"  New Hunter credits: {this_run['hunter_credits']}",
        f"  New Hunter estimate: ${this_run['hunter_estimated_usd']}",
        f"  New Apify estimate: ${this_run['apify_usd']}",
        f"  Combined estimate for this run: ${report['estimated_total_usd']}",
        f"  Estimate per delivered row for this run: {per_row if per_row == 'n/a' else '$' + str(per_row)}",
        f"  Hunter credits skipped because the domain or email was already cached: {budget['hunter_credits_saved_by_cache']}",
        "",
        "Cache total (every run that used this cache folder)",
        f"  Hunter credits: {lifetime['hunter_credits']}",
        f"  Apify estimate: ${lifetime['apify_usd']}",
        f"  Credit cap: {budget['max_hunter_credits']}",
        f"  Apify cap: ${budget['max_apify_usd']}",
        "",
    ]
    warnings = report["warnings"]
    if isinstance(warnings, list) and warnings:
        lines.append("Attention")
        lines.extend(f"  {warning}" for warning in warnings)
        lines.append("")
    else:
        lines.append("This run finished without hitting the budget cap.")
        lines.append("")
    lines.extend(
        [
            "Stages",
            (
                f"  discover: {_count(discover['places_kept'], 'company', 'companies')} kept, "
                f"{_count(discover['runs'], 'Apify run')}, {_count(discover['cached_runs'], 'cached run')}, "
                f"{discover['skipped_no_name']} skipped (no name), "
                f"{discover['skipped_outside_area']} skipped (outside Texas)"
            ),
            (
                f"  enrich: {_count(enrich['with_email'], 'email')} found, "
                f"{_count(enrich['api_calls'], 'Hunter search', 'Hunter searches')}, "
                f"{_count(enrich['cache_hits'], 'cache hit')}, {_count(enrich['credits'], 'credit')}, "
                f"{enrich['skipped_no_domain']} skipped (no website), "
                f"{enrich['skipped_shared_host']} skipped (directory or website-builder host), "
                f"{enrich['skipped_disposable_domain']} skipped (disposable domain)"
            ),
            (
                f"  verify: {by_status.get('valid', 0)} valid, {by_status.get('risky', 0)} risky, "
                f"{by_status.get('invalid', 0)} invalid, {by_status.get('unknown', 0)} unknown, "
                f"{_count(verify['api_calls'], 'Hunter verification')}, {_count(verify['credits'], 'credit')}, "
                f"{verify['local_invalid']} rejected by free checks, "
                f"{verify['role_flagged']} role inboxes noted (still delivered when Hunter says valid)"
            ),
            (
                f"  clean: dropped {_count(clean['dupes_email'], 'duplicate email')}, "
                f"{_count(clean['dupes_domain'], 'duplicate domain')}, "
                f"{_count(clean['dupes_phone'], 'duplicate phone')}, "
                f"{clean['dropped_not_valid']} rows that were not valid, "
                f"{clean['dropped_missing']} rows missing a company or email"
            ),
            f"  export: {report['delivered_rows']} rows written",
            "",
            "Rate card used for the estimate",
            "  Edit these numbers in roofleads.toml if your plan charges something else.",
        ]
    )
    rate_card = report["rate_card"]
    assert isinstance(rate_card, dict)
    lines.append(
        f"  Hunter domain search: {_count(rate_card['hunter_credits_per_domain_search'], 'credit')}"
    )
    lines.append(f"  Hunter verification: {_count(rate_card['hunter_credits_per_verification'], 'credit')}")
    lines.append(f"  Dollar value used here: ${rate_card['hunter_usd_per_credit']} per Hunter credit")
    lines.append(
        "  Apify: "
        f"${rate_card['apify_usd_per_place']} per place, "
        f"${rate_card['apify_usd_per_filter']} per filter, "
        f"{rate_card['apify_filters_per_place']} filters, "
        f"${rate_card['apify_usd_per_start']} per run start"
    )
    lines.append(f"  {rate_card['note']}")
    lines.append("")
    return "\n".join(lines)


def write_reports(output_dir: Path, report: dict[str, object]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "qa_report.json"
    text_path = output_dir / "qa_report.txt"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(render_text_report(report), encoding="utf-8")
    return json_path, text_path
