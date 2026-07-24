"""Skill matching tests use only synthetic prose."""

from it_labor_market_intelligence.processing.skills import load_skill_taxonomy, match_skills


def test_taxonomy_loader_reads_seed_fields() -> None:
    taxonomy = load_skill_taxonomy()
    python = next(entry for entry in taxonomy if entry.canonical_name == "Python")
    assert "python3" in python.aliases
    assert python.category == "Programming languages"
    assert python.false_positive_note


def test_case_insensitive_alias_matching_and_deterministic_deduplication() -> None:
    text = "Required skills: PYTHON3, NodeJS, PostgreSQL, python and AWS."
    first = match_skills(text)
    second = match_skills(text)
    assert first == second
    assert [match.canonical_name for match in first] == [
        "Python",
        "Node.js",
        "PostgreSQL",
        "Amazon Web Services",
    ]
    assert text[first[0].start : first[0].end] == first[0].evidence_text


def test_boundaries_prevent_java_inside_javascript() -> None:
    matches = match_skills("Required experience: JavaScript")
    assert [match.canonical_name for match in matches] == ["JavaScript"]


def test_false_positive_exclusions_require_context() -> None:
    assert match_skills("We react to change, go beyond goals, and excel together.") == ()
    assert match_skills("The playwright wrote about the element selenium.") == ()


def test_vietnamese_diacritics_and_english_requirement_context() -> None:
    text = "Yêu cầu kỹ năng React framework, giao tiếp tiếng Anh và giải quyết vấn đề."
    names = [match.canonical_name for match in match_skills(text)]
    assert names == ["React", "Communication", "English", "Problem solving"]


def test_null_and_empty_skill_text_return_empty_result() -> None:
    assert match_skills(None) == ()
    assert match_skills("") == ()
