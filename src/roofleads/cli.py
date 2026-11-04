import argparse
import os
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from roofleads.clean import clean_leads
from roofleads.config import load_settings
from roofleads.envfile import load_dotenv
from roofleads.errors import ApiError, ConfigError, ExportError
from roofleads.export import build_report, read_jsonl, write_csv, write_jsonl, write_reports
from roofleads.logsetup import configure_logging
from roofleads.models import RunStats, lead_from_record, utc_stamp
from roofleads.pipeline import discover_all, enrich_lead, run_pipeline, verify_lead
from roofleads.runtime import Runtime, build_runtime

MISSING_APIFY = (
    "APIFY_TOKEN is not set. Add it to the .env file in this folder "
    "(see .env.example). Create a token in the Apify console under Settings → API tokens. "
    "A practice run does not need a token:\n"
    "  python -m roofleads run --dry-run"
)
MISSING_HUNTER = (
    "HUNTER_API_KEY is not set. Add it to the .env file in this folder "
    "(see .env.example). Create a key in your Hunter account. "
    "A practice run does not need a key:\n"
    "  python -m roofleads run --dry-run"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roofleads",
        description="Build a checked list of Texas roofing companies with business emails.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--config", default="roofleads.toml", help="Path to roofleads.toml")
        command.add_argument("--output-dir", default="out", help="Folder for CSV, QA, and stage files")
        command.add_argument("--cache-dir", default=None, help="Folder that remembers paid lookups")
        command.add_argument("--dry-run", action="store_true", help="Use bundled sample companies and mock the APIs")
        command.add_argument("--fixtures", action="store_true", help="Same as --dry-run")
        command.add_argument("--max-credits", type=int, default=None, help="Hunter credit cap for this cache")
        command.add_argument("--max-apify-usd", type=float, default=None, help="Apify dollar cap for this cache")
        command.add_argument("--verbose", action="store_true", help="Log one JSON line per API call")

    discover = sub.add_parser("discover", help="Find roofing companies with the Apify Google Maps actor")
    add_common(discover)

    enrich = sub.add_parser("enrich", help="Find a business email and public owner name with Hunter")
    add_common(enrich)
    enrich.add_argument("--input", default=None, help="discovered.jsonl from the discover stage")

    verify = sub.add_parser("verify", help="Check emails with free tests, then Hunter")
    add_common(verify)
    verify.add_argument("--input", default=None, help="enriched.jsonl from the enrich stage")
    verify.add_argument(
        "--smtp-probe",
        action="store_true",
        help=(
            "Also open port 25 and send RCPT. Off by default. Risky: providers treat this as abuse, "
            "the port is often blocked, and the answer is unreliable. Hunter still decides delivery."
        ),
    )

    clean = sub.add_parser("clean", help="Normalize, drop incomplete rows, and remove duplicates")
    add_common(clean)
    clean.add_argument("--input", default=None, help="verified.jsonl from the verify stage")

    export = sub.add_parser("export", help="Write the CSV and a QA report")
    add_common(export)
    export.add_argument("--input", default=None, help="cleaned.jsonl from the clean stage")

    run = sub.add_parser("run", help="Run discover, enrich, verify, clean, and export")
    add_common(run)
    run.add_argument("--target-rows", type=int, default=100, help="How many checked rows to write")
    run.add_argument(
        "--smtp-probe",
        action="store_true",
        help=(
            "Also open port 25 and send RCPT. Off by default. Risky: providers treat this as abuse, "
            "the port is often blocked, and the answer is unreliable. Hunter still decides delivery."
        ),
    )
    return parser


def _prepare(args: argparse.Namespace, *, need_apify: bool, need_hunter: bool) -> tuple[Runtime, Path]:
    load_dotenv(Path.cwd() / ".env")
    dry = bool(args.dry_run or args.fixtures)
    secrets: list[str] = []
    token = ""
    hunter_key = ""
    if not dry and need_apify:
        token = os.environ.get("APIFY_TOKEN", "").strip()
        if not token:
            raise ConfigError(MISSING_APIFY)
        secrets.append(token)
    if not dry and need_hunter:
        hunter_key = os.environ.get("HUNTER_API_KEY", "").strip()
        if not hunter_key:
            raise ConfigError(MISSING_HUNTER)
        secrets.append(hunter_key)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(bool(args.verbose), secrets, output_dir / "roofleads.log")
    settings = load_settings(Path(args.config))
    overrides: dict[str, object] = {}
    if args.max_credits is not None:
        if args.max_credits < 0:
            raise ConfigError("--max-credits cannot be negative.")
        overrides["max_credits"] = args.max_credits
    if args.max_apify_usd is not None:
        if args.max_apify_usd < 0:
            raise ConfigError("--max-apify-usd cannot be negative.")
        overrides["max_apify_usd"] = Decimal(str(args.max_apify_usd))
    if getattr(args, "smtp_probe", False):
        overrides["smtp_probe"] = True
    if overrides:
        settings = replace(settings, **overrides)
    mode = "dry-run" if dry else "live"
    cache_dir = Path(args.cache_dir) if args.cache_dir else Path(".cache") / "roofleads" / mode
    runtime = build_runtime(
        settings,
        cache_path=cache_dir / "cache.json",
        mode=mode,
        token=token,
        hunter_key=hunter_key,
        secrets=secrets,
    )
    return runtime, output_dir


def _input_path(args: argparse.Namespace, default_name: str) -> Path:
    if args.input:
        return Path(args.input)
    return Path(args.output_dir) / default_name


def _print_stop(runtime: Runtime) -> None:
    if runtime.budget.stopped_reason:
        print(runtime.budget.stopped_reason)


def cmd_run(args: argparse.Namespace) -> int:
    if args.target_rows < 1:
        raise ConfigError("--target-rows must be at least 1.")
    runtime, output_dir = _prepare(args, need_apify=True, need_hunter=True)
    try:
        result = run_pipeline(runtime, output_dir, args.target_rows)
    finally:
        runtime.http.close()
    print(f"Wrote {result.delivered} rows to {result.csv_path}")
    print(f"QA report: {result.qa_text_path}")
    if result.stopped_reason:
        print(result.stopped_reason)
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        return 1
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    runtime, output_dir = _prepare(args, need_apify=True, need_hunter=False)
    try:
        leads = discover_all(runtime)
        path = output_dir / "discovered.jsonl"
        write_jsonl(path, [lead.to_record() for lead in leads])
    finally:
        runtime.http.close()
    print(f"Discovered {len(leads)} companies → {path}")
    _print_stop(runtime)
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    runtime, output_dir = _prepare(args, need_apify=False, need_hunter=True)
    try:
        leads = [lead_from_record(row) for row in read_jsonl(_input_path(args, "discovered.jsonl"))]
        enriched = []
        for lead in leads:
            if runtime.budget.stopped_reason:
                break
            contact = enrich_lead(runtime, lead)
            if contact is None:
                break
            enriched.append(contact)
        path = output_dir / "enriched.jsonl"
        write_jsonl(path, [lead.to_record() for lead in enriched])
    finally:
        runtime.http.close()
    print(f"Enriched {len(enriched)} companies → {path}")
    _print_stop(runtime)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    runtime, output_dir = _prepare(args, need_apify=False, need_hunter=True)
    try:
        leads = [lead_from_record(row) for row in read_jsonl(_input_path(args, "enriched.jsonl"))]
        checked = []
        for lead in leads:
            if runtime.budget.stopped_reason:
                break
            result = verify_lead(runtime, lead)
            if result is None:
                break
            checked.append(result)
        path = output_dir / "verified.jsonl"
        write_jsonl(path, [lead.to_record() for lead in checked])
    finally:
        runtime.http.close()
    print(f"Checked {len(checked)} emails → {path}")
    _print_stop(runtime)
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    runtime, output_dir = _prepare(args, need_apify=False, need_hunter=False)
    try:
        leads = [lead_from_record(row) for row in read_jsonl(_input_path(args, "verified.jsonl"))]
        cleaned = clean_leads(leads, stamp=utc_stamp(runtime.clock), stats=runtime.stats)
        path = output_dir / "cleaned.jsonl"
        write_jsonl(path, [lead.to_record() for lead in cleaned])
    finally:
        runtime.http.close()
    print(f"Kept {len(cleaned)} companies → {path}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    runtime, output_dir = _prepare(args, need_apify=False, need_hunter=False)
    try:
        leads = [lead_from_record(row) for row in read_jsonl(_input_path(args, "cleaned.jsonl"))]
        csv_path = output_dir / "leads.csv"
        write_csv(csv_path, leads)
        stats = RunStats(clean_kept=len(leads), delivered=len(leads))
        report = build_report(
            stats=stats,
            budget=runtime.budget,
            settings=runtime.settings,
            mode=runtime.mode,
            target_rows=len(leads),
            delivered=leads,
            generated_at=utc_stamp(runtime.clock),
            output_dir=output_dir,
        )
        warnings = report["warnings"]
        if isinstance(warnings, list):
            warnings.append(
                "This report was built from the cleaned file. "
                "Run `python -m roofleads run` when you want stage counts and this-run cost."
            )
        _json_path, text_path = write_reports(output_dir, report)
    finally:
        runtime.http.close()
    print(f"Wrote {len(leads)} rows to {csv_path}")
    print(f"QA report: {text_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "run": cmd_run,
        "discover": cmd_discover,
        "enrich": cmd_enrich,
        "verify": cmd_verify,
        "clean": cmd_clean,
        "export": cmd_export,
    }
    try:
        handler = commands[args.command]
        return handler(args)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (ExportError, ApiError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def console_main() -> None:
    raise SystemExit(main())
