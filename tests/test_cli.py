import csv
import json
import smtplib
from pathlib import Path

from roofleads.cli import MISSING_HUNTER, main
from roofleads.config import DEFAULT_CITIES
from roofleads.fixtures import BANNED_MARKER, BANNED_PHONE
from roofleads.models import CSV_COLUMNS
from roofleads.sample_data import CEDAR_EMAIL, CEDAR_NAME, CEDAR_OWNER


def test_shipped_config_matches_the_practice_cities(settings) -> None:
    assert settings.cities == DEFAULT_CITIES
    assert settings.actor_id == "compass/crawler-google-places"
    assert settings.max_credits >= 100
    assert settings.smtp_probe is False


def test_missing_keys_name_the_variable(tmp_path, repo_root, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    code = main(
        [
            "run",
            "--config",
            str(repo_root / "roofleads.toml"),
            "--output-dir",
            str(tmp_path / "out"),
            "--target-rows",
            "1",
        ]
    )
    assert code == 2
    error = capsys.readouterr().err
    assert "APIFY_TOKEN is not set" in error
    assert "python -m roofleads run --dry-run" in error
    assert MISSING_HUNTER.startswith("HUNTER_API_KEY is not set")


def test_dry_run_command_writes_100_rows(tmp_path, repo_root, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("SMTP should not be used")

    monkeypatch.setattr(smtplib.SMTP, "__init__", explode)
    monkeypatch.setattr(smtplib.SMTP_SSL, "__init__", explode)
    output = tmp_path / "out"
    cache = tmp_path / "cache"
    code = main(
        [
            "run",
            "--dry-run",
            "--fixtures",
            "--target-rows",
            "100",
            "--config",
            str(repo_root / "roofleads.toml"),
            "--output-dir",
            str(output),
            "--cache-dir",
            str(cache),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "Wrote 100 rows" in captured.out
    csv_path = output / "leads.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(CSV_COLUMNS)
        rows = list(reader)
    assert len(rows) == 100
    assert {row["email_status"] for row in rows} == {"valid"}
    assert all(row["company_name"] and row["email"] for row in rows)
    assert len({row["email"] for row in rows}) == 100
    assert len({row["website"] for row in rows}) == 100
    phones = [row["phone"] for row in rows if row["phone"]]
    assert len(phones) == len(set(phones))
    cities = [row["city"] for row in rows]
    assert cities == sorted(cities)
    cedar = next(row for row in rows if row["company_name"] == CEDAR_NAME)
    assert cedar["owner_name"] == CEDAR_OWNER
    assert cedar["email"] == CEDAR_EMAIL
    assert cedar["phone"] == "+15125550140"
    assert cedar["website"] == "https://cedarpostroof.example"
    assert cedar["source"].startswith("apify:compass/crawler-google-places")
    text = csv_path.read_text(encoding="utf-8")
    assert "Hill, Mesa & Co. Roofing" in text
    assert "Peña Roofing" in text
    assert text.count("+15125550140") == 1
    assert "info@lonestar-roof-pros.example" in text
    assert text.count("info@lonestar-roof-pros.example") == 1
    raw = csv_path.read_bytes()
    assert raw.startswith("company_name,".encode())
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "Peña".encode() in raw
    report = json.loads((output / "qa_report.json").read_text(encoding="utf-8"))
    assert report["delivered_rows"] == 100
    assert report["meets_quality_target"] is True
    assert report["mode"] == "dry-run"
    assert float(report["delivered_valid_rate"]) == 1
    stages = report["stages"]
    assert stages["discover"]["skipped_no_name"] >= 1
    assert stages["discover"]["skipped_outside_area"] >= 1
    assert stages["enrich"]["skipped_shared_host"] >= 1
    assert stages["enrich"]["skipped_disposable_domain"] >= 1
    assert stages["verify"]["local_invalid"] >= 1
    assert stages["verify"]["by_status"]["valid"] >= 100
    assert stages["verify"]["by_status"]["risky"] >= 1
    assert stages["verify"]["by_status"]["invalid"] >= 1
    assert stages["verify"]["by_status"]["unknown"] >= 1
    assert stages["clean"]["dupes_email"] >= 1
    assert stages["clean"]["dupes_phone"] >= 1
    assert report["budget"]["this_run"]["hunter_credits"] > 0
    qa_text = (output / "qa_report.txt").read_text(encoding="utf-8")
    assert "Delivered 100 of 100 requested rows." in qa_text
    cache_text = (cache / "cache.json").read_text(encoding="utf-8")
    blob = cache_text + text + (output / "discovered.jsonl").read_text(encoding="utf-8")
    assert BANNED_MARKER not in blob
    assert BANNED_PHONE not in blob
    assert "owner.personal@gmail.com" not in blob
    assert "Sooner Roofing" not in (output / "discovered.jsonl").read_text(encoding="utf-8")

    second = main(
        [
            "run",
            "--dry-run",
            "--target-rows",
            "100",
            "--config",
            str(repo_root / "roofleads.toml"),
            "--output-dir",
            str(tmp_path / "out2"),
            "--cache-dir",
            str(cache),
        ]
    )
    assert second == 0
    second_report = json.loads((tmp_path / "out2" / "qa_report.json").read_text(encoding="utf-8"))
    assert second_report["delivered_rows"] == 100
    assert second_report["budget"]["this_run"]["hunter_credits"] == 0
    assert second_report["budget"]["this_run"]["apify_usd"] == "0.000000"
    assert second_report["budget"]["lifetime"]["hunter_credits"] == report["budget"]["lifetime"]["hunter_credits"]


def test_clean_and_export_commands(tmp_path, repo_root, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    verified = tmp_path / "verified.jsonl"
    verified.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "company_name": "Alpha Roofing",
                        "email": "info@alpha.example",
                        "website": "https://www.alpha.example/contact",
                        "phone": "(512) 555-0101",
                        "city": "Austin",
                        "email_status": "valid",
                        "source": "apify:test+hunter:domain-search",
                        "seq": 1,
                    }
                ),
                json.dumps(
                    {
                        "company_name": "Alpha Branch",
                        "email": "houston@shop.alpha.example",
                        "website": "https://shop.alpha.example",
                        "phone": "(713) 555-0199",
                        "city": "Houston",
                        "email_status": "valid",
                        "source": "apify:test+hunter:domain-search",
                        "seq": 2,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "out"
    code = main(
        [
            "clean",
            "--dry-run",
            "--config",
            str(repo_root / "roofleads.toml"),
            "--input",
            str(verified),
            "--output-dir",
            str(output),
            "--cache-dir",
            str(tmp_path / "cache"),
        ]
    )
    assert code == 0
    cleaned = (output / "cleaned.jsonl").read_text(encoding="utf-8")
    assert "info@alpha.example" in cleaned
    assert "houston@shop.alpha.example" not in cleaned
    code = main(
        [
            "export",
            "--dry-run",
            "--config",
            str(repo_root / "roofleads.toml"),
            "--input",
            str(output / "cleaned.jsonl"),
            "--output-dir",
            str(output),
            "--cache-dir",
            str(tmp_path / "cache"),
        ]
    )
    assert code == 0
    exported = (output / "leads.csv").read_text(encoding="utf-8")
    assert "info@alpha.example" in exported
    assert "houston@shop.alpha.example" not in exported


def test_repo_hygiene(repo_root: Path) -> None:
    ignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in ignore
    assert ".cache/" in ignore
    assert "out/" in ignore
    example = (repo_root / ".env.example").read_text(encoding="utf-8")
    assert "APIFY_TOKEN=" in example
    assert "HUNTER_API_KEY=" in example
    assert "apify_api_" not in example


