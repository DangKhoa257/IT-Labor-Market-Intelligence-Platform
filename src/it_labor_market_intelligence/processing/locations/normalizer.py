"""Deterministic Vietnam city, district, and remote normalization."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from it_labor_market_intelligence.processing.text import comparison_key

_REMOTE = re.compile(r"\b(?:remote|work from home|wfh|làm việc từ xa|flexible location)\b", re.I)
_DISTRICT = re.compile(r"\b(?:quận|q\.)\s*([0-9]+)\b|\b(thủ đức)\b", re.I)


def _cities(path: Path | None = None) -> dict[str, tuple[str, ...]]:
    reference = (
        path
        or Path(__file__).resolve().parents[4] / "datasets" / "reference" / "vietnam_locations.json"
    )
    payload = json.loads(reference.read_text(encoding="utf-8"))
    return {city: tuple(aliases) for city, aliases in payload["cities"].items()}


def normalize_location(value: str | None, reference_path: Path | None = None) -> dict[str, Any]:
    key = comparison_key(value)
    if key is None:
        return {
            "location_raw": value,
            "city": None,
            "province": None,
            "district": None,
            "country": None,
            "normalized_locations": (),
            "is_remote_only": False,
            "confidence": 1.0,
            "provenance": {
                "source_field": "location_raw",
                "method": "null_semantics",
                "rule_version": "location.v1",
                "confidence": 1.0,
                "evidence_text": value,
            },
        }
    matches: list[str] = []
    for city, aliases in _cities(reference_path).items():
        alias_keys = (comparison_key(alias) for alias in aliases)
        if any(alias_key is not None and alias_key in key for alias_key in alias_keys):
            matches.append(city)
    district_match = _DISTRICT.search(value or "")
    district = None
    if district_match:
        district = f"District {district_match.group(1)}" if district_match.group(1) else "Thu Duc"
    remote = bool(_REMOTE.search(value or ""))
    physical = tuple(dict.fromkeys(matches))
    return {
        "location_raw": value,
        "city": physical[0] if len(physical) == 1 else None,
        "province": physical[0] if len(physical) == 1 else None,
        "district": district,
        "country": "Vietnam" if physical else None,
        "normalized_locations": physical,
        "is_remote_only": remote and not physical,
        "confidence": 0.95 if physical or remote else 0.0,
        "provenance": {
            "source_field": "location_raw",
            "method": "alias_location_match",
            "rule_version": "location.v1",
            "confidence": 0.95 if physical or remote else 0.0,
            "evidence_text": value,
        },
    }
