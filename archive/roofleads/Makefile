PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: install test dry-run run

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"

test:
	$(PY) -m pytest

dry-run:
	$(PY) -m roofleads run --dry-run --target-rows 100

run:
	$(PY) -m roofleads run --target-rows 100
