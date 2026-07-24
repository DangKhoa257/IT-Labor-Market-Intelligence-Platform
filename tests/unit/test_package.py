"""Tests for the minimal Phase 0 Python package."""

import tomllib
from pathlib import Path

import it_labor_market_intelligence

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_package_can_be_imported() -> None:
    assert it_labor_market_intelligence.__version__ == "0.1.0"


def test_phase_zero_packaging_configuration() -> None:
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        configuration = tomllib.load(pyproject_file)

    assert configuration["project"]["requires-python"] == ">=3.12,<3.14"
    assert configuration["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/it_labor_market_intelligence"
    ]

    dev_dependencies = configuration["project"]["optional-dependencies"]["dev"]
    dependency_names = {dependency.split(">=", maxsplit=1)[0] for dependency in dev_dependencies}
    assert {"pytest", "pytest-cov", "ruff", "black", "mypy"} <= dependency_names
