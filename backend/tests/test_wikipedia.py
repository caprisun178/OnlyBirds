"""`app/dao/wikipedia.py` — section-matching logic tested directly against
canned section lists/extract text, not live Wikipedia (offline-tests rule,
docs/ebird-api.md). The actual HTTP calls were live-verified once by hand
while building this (see docs/features/bird-info.md's build order) and are
mocked everywhere else in the suite via conftest.py's autouse fixture.
"""

from app.dao.wikipedia import _extract_matching_sections


def test_matches_description_and_combined_habitat_section():
    sections = [
        {"index": "1", "line": "Taxonomy", "toclevel": 1},
        {"index": "2", "line": "Description", "toclevel": 1},
        {"index": "3", "line": "Distribution and habitat", "toclevel": 1},
        {"index": "4", "line": "References", "toclevel": 1},
    ]
    full_text = (
        "Intro paragraph.\n\n"
        "Taxonomy\n"
        "Taxonomy text here.\n\n"
        "Description\n"
        "Males and females look alike.\n\n"
        "Distribution and habitat\n"
        "Found in forests year-round.\n\n"
        "References\n"
        "Some citation."
    )
    result = _extract_matching_sections(full_text, sections)
    assert result["sex_differences"] == "Males and females look alike."
    assert result["habitat"] == "Found in forests year-round."
    # No standalone "Migration" heading — falls back to the combined section.
    assert result["migration"] == "Found in forests year-round."


def test_standalone_migration_section_is_used_over_the_habitat_fallback():
    sections = [
        {"index": "1", "line": "Habitat", "toclevel": 1},
        {"index": "2", "line": "Migration", "toclevel": 1},
    ]
    full_text = "Habitat\nLives in wetlands.\n\nMigration\nWinters in South America."
    result = _extract_matching_sections(full_text, sections)
    assert result["habitat"] == "Lives in wetlands."
    assert result["migration"] == "Winters in South America."


def test_subsections_are_included_in_the_parent_sections_text():
    sections = [
        {"index": "1", "line": "Distribution and habitat", "toclevel": 1},
        {"index": "2", "line": "Breeding range", "toclevel": 2},
        {"index": "3", "line": "Conservation", "toclevel": 1},
    ]
    full_text = (
        "Distribution and habitat\n"
        "Found across North America.\n\n"
        "Breeding range\n"
        "Breeds in the boreal forest.\n\n"
        "Conservation\n"
        "Least concern."
    )
    result = _extract_matching_sections(full_text, sections)
    assert "Found across North America." in result["habitat"]
    assert "Breeds in the boreal forest." in result["habitat"]
    assert "Least concern." not in result["habitat"]


def test_no_matching_sections_returns_empty_dict():
    sections = [
        {"index": "1", "line": "Taxonomy", "toclevel": 1},
        {"index": "2", "line": "Cultural significance", "toclevel": 1},
    ]
    full_text = "Taxonomy\nSome text.\n\nCultural significance\nMore text."
    assert _extract_matching_sections(full_text, sections) == {}


def test_a_heading_not_found_verbatim_in_the_extract_is_skipped_not_crashed():
    # Can happen if the plain-text extract renders a heading slightly
    # differently than the sections API's title (rare, but shouldn't 500).
    sections = [{"index": "1", "line": "Habitat", "toclevel": 1}]
    full_text = "Some unrelated intro text with no matching heading line at all."
    assert _extract_matching_sections(full_text, sections) == {}
