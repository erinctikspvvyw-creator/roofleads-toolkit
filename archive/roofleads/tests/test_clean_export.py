from pathlib import Path

import pytest

from roofleads.clean import clean_leads
from roofleads.errors import ExportError
from roofleads.export import write_csv
from roofleads.models import CSV_COLUMNS, Lead


def _lead(**kwargs: object) -> Lead:
    base = dict(
        company_name="Alpha Roofing",
        owner_name="Ada Owner",
        email="info@alpha.example",
        website="https://www.alpha.example/contact",
        phone="(512) 555-0101",
        city="Austin",
        email_status="valid",
        source="apify:test+hunter:domain-search",
        seq=1,
    )
    base.update(kwargs)
    return Lead(**base)  # type: ignore[arg-type]


def test_clean_drops_incomplete_and_duplicate_rows() -> None:
    rows = [
        _lead(seq=1),
        _lead(company_name="Alpha Copy", email="INFO@alpha.example", seq=2),
        _lead(
            company_name="Alpha Branch",
            email="houston@shop.alpha.example",
            website="https://shop.alpha.example",
            phone="(713) 555-0199",
            city="Houston",
            seq=3,
        ),
        _lead(
            company_name="Beta Roofing",
            email="info@beta.example",
            website="https://beta.example",
            phone="512.555.0101",
            seq=4,
        ),
        _lead(company_name="", email="info@blank.example", website="https://blank.example", phone="(214) 555-0170", seq=5),
        _lead(email="", seq=6),
        _lead(
            company_name="Risky Roofing",
            email="info@risky.example",
            website="https://risky.example",
            email_status="risky",
            seq=7,
        ),
    ]
    kept = clean_leads(rows, stamp="2026-11-03T15:04:00Z")
    emails = [lead.email for lead in kept]
    assert emails == ["info@alpha.example"]
    assert kept[0].phone == "+15125550101"
    assert kept[0].website == "https://alpha.example"
    assert kept[0].collected_at == "2026-11-03T15:04:00Z"


def test_same_score_keeps_the_earlier_row() -> None:
    rows = [
        _lead(company_name="First Roofing", email="info@first.example", website="https://first.example", seq=1),
        _lead(
            company_name="Second Roofing",
            email="info@second.example",
            website="https://second.example",
            phone="(512) 555-0101",
            seq=2,
        ),
    ]
    kept = clean_leads(rows, stamp="2026-11-03T15:04:00Z")
    assert [lead.company_name for lead in kept] == ["First Roofing"]


def test_export_refuses_rows_that_are_not_deliverable(tmp_path: Path) -> None:
    path = tmp_path / "leads.csv"
    with pytest.raises(ExportError):
        write_csv(path, [_lead(email_status="risky")])
    good = _lead()
    cleaned = clean_leads([good], stamp="2026-11-03T15:04:00Z")
    write_csv(path, cleaned)
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == list(CSV_COLUMNS)
