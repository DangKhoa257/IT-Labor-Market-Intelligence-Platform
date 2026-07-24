"""Structured-first employment type normalization."""

from __future__ import annotations

import re
from typing import Any

_RULES = (
    ("INTERNSHIP", r"\b(?:internship|intern|th\u1ef1c t\u1eadp)\b"),
    ("PART_TIME", r"\b(?:part[ -]?time|b\u00e1n th\u1eddi gian)\b"),
    ("FULL_TIME", r"\b(?:full[ -]?time|to\u00e0n th\u1eddi gian)\b"),
    ("FREELANCE", r"\bfreelance\b"),
    ("APPRENTICESHIP", r"\b(?:apprenticeship|h\u1ecdc vi\u1ec7c)\b"),
    ("TEMPORARY", r"\b(?:temporary|t\u1ea1m th\u1eddi)\b"),
    ("CONTRACT", r"\b(?:contract|h\u1ee3p \u0111\u1ed3ng)\b"),
)


def normalize_employment_type(
    raw_value: str | None, fallback_text: str | None = None
) -> dict[str, Any]:
    """Map explicit source value first; ``OTHER`` intentionally remains unspecified."""
    raw = raw_value.strip() if raw_value else None
    candidates = ((raw, "employment_type_raw", 0.98), (fallback_text, "title_or_description", 0.75))
    for text, source_field, confidence in candidates:
        if not text or text.casefold() == "other":
            continue
        for value, pattern in _RULES:
            if match := re.search(pattern, text, re.I):
                return {
                    "employment_type_raw": raw_value,
                    "employment_type": value,
                    "confidence": confidence,
                    "evidence": match.group(),
                    "provenance": {
                        "source_field": source_field,
                        "method": "structured_first_regex",
                        "rule_version": "employment.v1",
                        "confidence": confidence,
                        "evidence_text": match.group(),
                    },
                }
    confidence = 1.0 if raw is None or raw.casefold() == "other" else 0.0
    return {
        "employment_type_raw": raw_value,
        "employment_type": "UNSPECIFIED",
        "confidence": confidence,
        "evidence": None,
        "provenance": {
            "source_field": "employment_type_raw",
            "method": "unspecified",
            "rule_version": "employment.v1",
            "confidence": confidence,
            "evidence_text": raw_value,
        },
    }
