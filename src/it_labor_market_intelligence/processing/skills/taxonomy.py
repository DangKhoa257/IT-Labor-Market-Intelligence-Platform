"""Loader for the version-controlled Markdown skill taxonomy seed."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TAXONOMY_VERSION = "skill-taxonomy.v1"


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """One canonical taxonomy entry."""

    canonical_name: str
    aliases: tuple[str, ...]
    category: str
    false_positive_note: str


def default_taxonomy_path() -> Path:
    """Return the repository seed path; callers may inject another versioned seed."""

    return Path(__file__).resolve().parents[4] / "docs" / "SKILL_TAXONOMY.md"


def load_skill_taxonomy(path: Path | None = None) -> tuple[SkillDefinition, ...]:
    """Load taxonomy rows in document order and validate canonical/alias uniqueness."""

    taxonomy_path = path or default_taxonomy_path()
    entries: list[SkillDefinition] = []
    for line in taxonomy_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 4 or cells[0] == "Canonical name":
            continue
        canonical, aliases_text, category, false_positive_note = cells
        aliases = tuple(alias.strip() for alias in aliases_text.split(",") if alias.strip())
        entries.append(SkillDefinition(canonical, aliases, category, false_positive_note))

    if not entries:
        raise ValueError(f"no skill entries found in {taxonomy_path}")
    canonical_keys = [entry.canonical_name.casefold() for entry in entries]
    if len(canonical_keys) != len(set(canonical_keys)):
        raise ValueError("canonical skill names must be unique")
    alias_owner: dict[str, str] = {}
    for entry in entries:
        for alias in (entry.canonical_name, *entry.aliases):
            key = alias.casefold()
            previous = alias_owner.setdefault(key, entry.canonical_name)
            if previous != entry.canonical_name:
                raise ValueError(
                    f"alias {alias!r} maps to both {previous!r} and {entry.canonical_name!r}"
                )
    return tuple(entries)
