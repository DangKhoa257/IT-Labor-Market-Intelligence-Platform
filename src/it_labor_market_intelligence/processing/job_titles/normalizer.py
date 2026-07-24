"""Rule-based baseline derived from ``docs/JOB_TAXONOMY.md``."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from it_labor_market_intelligence.domain import FieldProvenance

RULE_VERSION = "job-taxonomy.v1"


@dataclass(frozen=True, slots=True)
class TitleNormalization:
    """Deterministic title/category result; confidence is rule confidence, not ML accuracy."""

    title_raw: str
    title_normalized: str
    primary_category: str
    secondary_categories: tuple[str, ...]
    confidence: float
    matched_rules: tuple[str, ...]
    provenance: FieldProvenance


_CATEGORY_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("Full-stack", "full_stack", re.compile(r"\bfull[\s-]?stack\b", re.I)),
    (
        "AI/Machine Learning",
        "ai_ml",
        re.compile(
            r"\b(?:ai|ml|machine learning|nlp|computer vision|mlops)\s+"
            r"(?:engineer|developer|scientist)\b",
            re.I,
        ),
    ),
    (
        "Data Scientist",
        "data_scientist",
        re.compile(r"\b(?:data|decision|applied)\s+scientist\b", re.I),
    ),
    (
        "Data Engineer",
        "data_engineer",
        re.compile(
            r"\b(?:data|big data|data platform|analytics)\s+engineer\b|\betl\s+developer\b",
            re.I,
        ),
    ),
    (
        "Business Intelligence",
        "business_intelligence",
        re.compile(
            r"\b(?:business intelligence|bi|power bi)\s+(?:developer|engineer|analyst)\b",
            re.I,
        ),
    ),
    (
        "Data Analyst",
        "data_analyst",
        re.compile(r"\b(?:data|product|marketing|reporting)\s+analyst\b", re.I),
    ),
    (
        "DevOps/Cloud/SRE",
        "devops_cloud_sre",
        re.compile(
            r"\b(?:devops|cloud|platform|site reliability|sre|infrastructure)\s+"
            r"(?:engineer|architect)\b|\bsite reliability\b",
            re.I,
        ),
    ),
    (
        "Cybersecurity",
        "cybersecurity",
        re.compile(
            r"\b(?:cyber ?security|security|soc|infosec|appsec)\s+"
            r"(?:engineer|analyst|specialist)|\bpenetration tester\b",
            re.I,
        ),
    ),
    (
        "Mobile",
        "mobile",
        re.compile(
            r"\b(?:mobile(?: app)?|android|ios|flutter|react native)\s+"
            r"(?:developer|engineer)\b",
            re.I,
        ),
    ),
    (
        "QA/Testing",
        "qa_testing",
        re.compile(
            r"\b(?:qa|qc|sdet|test(?: automation)?|manual test)\s*"
            r"(?:engineer|tester)?\b|\btester\b",
            re.I,
        ),
    ),
    (
        "Embedded/IoT",
        "embedded_iot",
        re.compile(
            r"\b(?:embedded(?: software)?|firmware|iot|bsp)\s+(?:developer|engineer)\b",
            re.I,
        ),
    ),
    (
        "ERP",
        "erp",
        re.compile(
            r"\b(?:sap|erp|dynamics 365|oracle erp|odoo)\s+" r"(?:consultant|developer|engineer)\b",
            re.I,
        ),
    ),
    (
        "Business Analyst",
        "business_analyst",
        re.compile(
            r"\b(?:business|system|requirements|functional|it ba)\s+analyst\b|\bit ba\b",
            re.I,
        ),
    ),
    (
        "Product Management",
        "product_management",
        re.compile(r"\b(?:technical )?product (?:manager|owner)\b", re.I),
    ),
    (
        "Project Management",
        "project_management",
        re.compile(
            r"\b(?:it |technical )?project manager\b|"
            r"\b(?:scrum master|delivery manager|project coordinator)\b",
            re.I,
        ),
    ),
    (
        "UI/UX",
        "ui_ux",
        re.compile(r"\b(?:ui(?:/ux)?|ux|product|interaction)\s+(?:designer|researcher)\b", re.I),
    ),
    (
        "IT Support/System Administration",
        "it_support",
        re.compile(
            r"\b(?:it|desktop)\s+support\b|\bhelp ?desk\b|"
            r"\b(?:system|network) administrator\b|\bsysadmin\b",
            re.I,
        ),
    ),
    (
        "Frontend",
        "frontend",
        re.compile(
            r"\b(?:front[\s-]?end|frontend|fe|web ui|react|vue|angular)\s+"
            r"(?:developer|engineer)\b",
            re.I,
        ),
    ),
    (
        "Backend",
        "backend",
        re.compile(
            r"\b(?:back[\s-]?end|backend|api|server[\s-]?side|java|\.net)\s+"
            r"(?:developer|engineer)\b",
            re.I,
        ),
    ),
)

_ACRONYMS = {
    "Ai": "AI",
    "Bi": "BI",
    "Erp": "ERP",
    "Fe": "FE",
    "Ios": "iOS",
    "Iot": "IoT",
    "It": "IT",
    "Ml": "ML",
    "Nlp": "NLP",
    "Qa": "QA",
    "Qc": "QC",
    "Sap": "SAP",
    "Sdet": "SDET",
    "Soc": "SOC",
    "Sre": "SRE",
    "Ui/Ux": "UI/UX",
    "Ux": "UX",
}


def _normalize_display_title(title: str) -> str:
    title = unicodedata.normalize("NFKC", title)
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"\bback[\s-]?end\b", "Backend", title, flags=re.I)
    title = re.sub(r"\bfront[\s-]?end\b", "Frontend", title, flags=re.I)
    title = re.sub(r"\bfull[\s-]?stack\b", "Full-stack", title, flags=re.I)
    titled = title.title()
    for generated, canonical in _ACRONYMS.items():
        titled = re.sub(rf"\b{re.escape(generated)}\b", canonical, titled)
    return titled


def normalize_job_title(title_raw: str) -> TitleNormalization:
    """Normalize a raw title and classify explicit title evidence only."""

    normalized_title = _normalize_display_title(title_raw)
    candidates: list[tuple[int, int, str, str]] = []
    for priority, (category, rule_name, pattern) in enumerate(_CATEGORY_RULES):
        if match := pattern.search(title_raw):
            candidates.append((match.start(), priority, category, rule_name))
    candidates.sort()

    categories: list[str] = []
    matched_rules: list[str] = []
    for _, _, category, rule_name in candidates:
        if category not in categories:
            categories.append(category)
            matched_rules.append(rule_name)

    if categories:
        primary = categories[0]
        secondary = tuple(categories[1:])
        confidence = 0.95 if len(categories) == 1 else 0.82
        method = "title_taxonomy_rule"
    else:
        primary = "Unclassified"
        secondary = ()
        confidence = 0.0
        matched_rules = ["fallback_unclassified"]
        method = "fallback"

    provenance = FieldProvenance(
        source_field="title_raw",
        method=method,
        rule_version=RULE_VERSION,
        confidence=confidence,
        evidence_text=title_raw,
    )
    return TitleNormalization(
        title_raw=title_raw,
        title_normalized=normalized_title,
        primary_category=primary,
        secondary_categories=secondary,
        confidence=confidence,
        matched_rules=tuple(matched_rules),
        provenance=provenance,
    )
