from dataclasses import replace
from pathlib import Path

import pytest

from roofleads.config import Settings, load_settings
from roofleads.runtime import Runtime, build_runtime
from roofleads.sample_data import SampleCompany


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def settings(repo_root: Path) -> Settings:
    return load_settings(repo_root / "roofleads.toml")


def make_runtime(
    tmp_path: Path,
    settings: Settings,
    companies: list[SampleCompany] | None = None,
    **overrides: object,
) -> Runtime:
    tuned = replace(settings, **overrides) if overrides else settings
    return build_runtime(
        tuned,
        cache_path=tmp_path / "cache.json",
        mode="dry-run",
        companies=companies,
        say=lambda _message: None,
    )
