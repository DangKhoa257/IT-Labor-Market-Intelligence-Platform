"""Deterministic JSON report serialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from it_labor_market_intelligence.data_io import atomic_write_text


def write_report(path: Path | str, report: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
