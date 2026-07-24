"""Conservative work-mode extraction with common false-positive exclusions."""

from __future__ import annotations

import re
from typing import Any

_RULES = (
    ("HYBRID", r"\b(?:hybrid|k\u1ebft h\u1ee3p)\b"),
    ("REMOTE", r"\b(?:remote work|work from home|wfh|l\u00e0m vi\u1ec7c t\u1eeb xa)\b"),
    ("FLEXIBLE", r"\b(?:flexible location|linh ho\u1ea1t \u0111\u1ecba \u0111i\u1ec3m)\b"),
    (
        "ONSITE",
        r"\b(?:on[ -]?site|t\u1ea1i v\u0103n ph\u00f2ng|l\u00e0m vi\u1ec7c tr\u1ef1c ti\u1ebfp)\b",
    ),
)
_FALSE_REMOTE = re.compile(r"\b(?:remote interview|support remote users)\b", re.I)


def normalize_work_mode(raw_value: str | None, fallback_text: str | None = None) -> dict[str, Any]:
    """Normalize structured value before text evidence; never infer onsite from absence."""
    raw = raw_value.strip() if raw_value else None
    texts = ((raw, "work_mode_raw", 0.98), (fallback_text, "title_or_description", 0.75))
    found: list[tuple[str, str, float, str]] = []
    for text, source, confidence in texts:
        if not text or _FALSE_REMOTE.search(text):
            continue
        for value, pattern in _RULES:
            if match := re.search(pattern, text, re.I):
                found.append((value, source, confidence, match.group()))
    if not found:
        confidence = 1.0 if raw is None else 0.0
        return {
            "work_mode_raw": raw_value,
            "work_mode": "UNSPECIFIED",
            "confidence": confidence,
            "evidence": None,
            "conflict": False,
            "provenance": {
                "source_field": "work_mode_raw",
                "method": "unspecified",
                "rule_version": "work-mode.v1",
                "confidence": confidence,
                "evidence_text": raw_value,
            },
        }
    selected = found[0]
    conflict = len({item[0] for item in found}) > 1
    return {
        "work_mode_raw": raw_value,
        "work_mode": selected[0],
        "confidence": selected[2] if not conflict else min(selected[2], 0.6),
        "evidence": selected[3],
        "conflict": conflict,
        "provenance": {
            "source_field": selected[1],
            "method": "structured_first_regex",
            "rule_version": "work-mode.v1",
            "confidence": selected[2],
            "evidence_text": selected[3],
        },
    }
