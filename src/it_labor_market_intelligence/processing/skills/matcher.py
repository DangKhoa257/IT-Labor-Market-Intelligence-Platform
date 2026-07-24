"""Boundary-aware, deterministic skill matching with conservative exclusions."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from it_labor_market_intelligence.domain import FieldProvenance, SkillMatch

from .taxonomy import TAXONOMY_VERSION, SkillDefinition, load_skill_taxonomy

_TECH_CONTEXT = re.compile(
    r"\b(?:skill|skills|experience|experienced|proficien(?:t|cy)|knowledge|developer|engineer|"
    r"framework|language|stack|required|requirements?|lập\s+trình|kỹ\s+năng|kinh\s+nghiệm|"
    r"thành\s+thạo|yêu\s+cầu)\b",
    re.IGNORECASE,
)
_LANGUAGE_CONTEXT = re.compile(
    r"\b(?:fluent|proficien(?:t|cy)|communication|written|spoken|required|language|"
    r"thành\s+thạo|giao\s+tiếp|đọc|viết|yêu\s+cầu|tiếng)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_TECH_ALIASES = {
    "angular",
    "excel",
    "flutter",
    "go",
    "js",
    "node",
    "py",
    "react",
    "spark",
    "spring",
    "tf",
    "torch",
    "ts",
    "vue",
}
_HUMAN_LANGUAGES = {"English", "Japanese", "Korean"}


def _alias_pattern(alias: str) -> re.Pattern[str]:
    parts = re.split(r"\s+", alias)
    body = r"\s+".join(re.escape(part) for part in parts)
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def _has_context(text: str, start: int, end: int, pattern: re.Pattern[str]) -> bool:
    window = text[max(0, start - 55) : min(len(text), end + 55)]
    return bool(pattern.search(window))


def _excluded(text: str, entry: SkillDefinition, alias: str, match: re.Match[str]) -> bool:
    key = alias.casefold()
    evidence = match.group()
    if key == "py" and match.start() > 0 and text[match.start() - 1] == ".":
        return True
    if key in _AMBIGUOUS_TECH_ALIASES and not _has_context(
        text, match.start(), match.end(), _TECH_CONTEXT
    ):
        return True
    if entry.canonical_name in _HUMAN_LANGUAGES and not _has_context(
        text, match.start(), match.end(), _LANGUAGE_CONTEXT
    ):
        return True
    if entry.canonical_name == "Selenium" and re.search(
        rf"\belement\s+{re.escape(evidence)}\b", text, re.IGNORECASE
    ):
        return True
    if entry.canonical_name == "Playwright" and re.search(
        rf"\b(?:the|a)\s+{re.escape(evidence)}\b", text, re.IGNORECASE
    ):
        return True
    return False


def match_skills(
    text: str | None,
    taxonomy: Sequence[SkillDefinition] | None = None,
    *,
    source_field: str = "description_raw",
) -> tuple[SkillMatch, ...]:
    """Return stable, canonical-deduplicated matches with exact evidence spans."""

    if text is None or not text:
        return ()
    normalized = unicodedata.normalize("NFC", text)
    entries = tuple(taxonomy) if taxonomy is not None else load_skill_taxonomy()
    candidates: list[tuple[int, int, str, SkillDefinition, str]] = []
    for entry in entries:
        aliases = (entry.canonical_name, *entry.aliases)
        for alias in aliases:
            for match in _alias_pattern(alias).finditer(normalized):
                if not _excluded(normalized, entry, alias, match):
                    candidates.append(
                        (match.start(), match.end(), entry.canonical_name, entry, alias)
                    )

    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2].casefold()))
    seen: set[str] = set()
    results: list[SkillMatch] = []
    for start, end, canonical_name, entry, alias in candidates:
        if canonical_name in seen:
            continue
        seen.add(canonical_name)
        evidence = normalized[start:end]
        confidence = 0.9 if alias.casefold() != canonical_name.casefold() else 0.95
        provenance = FieldProvenance(
            source_field=source_field,
            method="boundary_alias_match",
            rule_version=TAXONOMY_VERSION,
            confidence=confidence,
            evidence_text=evidence,
        )
        results.append(
            SkillMatch(
                canonical_name=canonical_name,
                matched_alias=alias,
                category=entry.category,
                start=start,
                end=end,
                evidence_text=evidence,
                confidence=confidence,
                provenance=provenance,
            )
        )
    return tuple(results)
