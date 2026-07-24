"""Conservative Vietnamese/English company normalization."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from it_labor_market_intelligence.processing.text import comparison_key, normalize_display

_HIDDEN = {"hidden company", "confidential", "ẩn danh", "n/a"}
_SUFFIXES = (
    ("joint stock company", "Joint Stock Company"),
    ("công ty cổ phần", "Công ty Cổ phần"),
    ("cong ty co phan", "Công ty Cổ phần"),
    ("công ty tnhh", "Công ty TNHH"),
    ("cong ty tnhh", "Công ty TNHH"),
    ("limited liability company", "LLC"),
    ("corporation", "Corporation"),
    ("company limited", "Limited"),
    ("limited", "Limited"),
    ("ltd", "Ltd"),
    ("llc", "LLC"),
    ("jsc", "JSC"),
    ("ctcp", "CTCP"),
    ("tnhh", "TNHH"),
    ("corp", "Corp"),
)


def _alias_map(path: Path | None = None) -> dict[str, str]:
    reference = (
        path
        or Path(__file__).resolve().parents[4] / "datasets" / "reference" / "company_aliases.json"
    )
    payload = json.loads(reference.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in payload.get("aliases", {}).items()}


def normalize_company(value: str | None, alias_path: Path | None = None) -> dict[str, Any]:
    """Return readable display text plus legal-suffix-free comparison key."""

    display = normalize_display(value)
    key = comparison_key(display)
    if display is None or key is None or key in _HIDDEN:
        return {
            "company_name_raw": value,
            "company_name_normalized": None,
            "company_comparison_key": None,
            "legal_suffix": None,
            "aliases_applied": (),
            "confidence": 1.0,
            "provenance": {
                "source_field": "company_name_raw",
                "method": "null_or_hidden",
                "rule_version": "company.v1",
                "confidence": 1.0,
                "evidence_text": value,
            },
        }
    aliases = _alias_map(alias_path)
    if key in aliases:
        canonical = aliases[key]
        return {
            "company_name_raw": value,
            "company_name_normalized": canonical,
            "company_comparison_key": comparison_key(canonical),
            "legal_suffix": None,
            "aliases_applied": (key,),
            "confidence": 0.99,
            "provenance": {
                "source_field": "company_name_raw",
                "method": "alias_map",
                "rule_version": "company.v1",
                "confidence": 0.99,
                "evidence_text": value,
            },
        }
    suffix: str | None = None
    comparison = key
    for suffix_key, suffix_display in _SUFFIXES:
        pattern = re.compile(rf"(?:^|\s){re.escape(suffix_key)}(?:$|\s)")
        if pattern.search(comparison):
            suffix = suffix_display
            comparison = pattern.sub(" ", comparison).strip()
            break
    return {
        "company_name_raw": value,
        "company_name_normalized": display,
        "company_comparison_key": comparison or key,
        "legal_suffix": suffix,
        "aliases_applied": (),
        "confidence": 0.95,
        "provenance": {
            "source_field": "company_name_raw",
            "method": "legal_suffix_comparison_key",
            "rule_version": "company.v1",
            "confidence": 0.95,
            "evidence_text": value,
        },
    }
