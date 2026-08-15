"""
tests/test_reference_data.py

Tests for reference_data.py. Covers:
  - listing available countries/industries returns the real data files
  - loading a known country/industry returns real, non-empty content
  - lookup is case-insensitive and tolerant of extra whitespace
  - an unknown country/industry returns None cleanly — never fabricated,
    never crashes
  - every loaded reference carries a source_note disclaimer (the "job
    description is the strongest source of truth" guarantee from the
    brief must always be present, not optional)
"""

import reference_data


def test_lists_available_countries_and_industries():
    countries = reference_data.list_available_countries()
    industries = reference_data.list_available_industries()

    assert "United Kingdom" in countries
    assert "United States" in countries
    assert "Healthcare" in industries
    assert "Technology" in industries
    assert "Finance" in industries


def test_loads_known_country_with_real_content():
    ref = reference_data.load_country_reference("United Kingdom")

    assert ref is not None
    assert ref.name == "United Kingdom"
    assert ref.key_conventions
    assert any("cv" in c.lower() for c in ref.key_conventions)


def test_loads_known_industry_with_real_content():
    ref = reference_data.load_industry_reference("Healthcare")

    assert ref is not None
    assert ref.name == "Healthcare"
    assert ref.key_conventions
    assert any("nhs" in c.lower() or "person specification" in c.lower() for c in ref.key_conventions)


def test_lookup_is_case_insensitive_and_whitespace_tolerant():
    ref_lower = reference_data.load_country_reference("united kingdom")
    ref_padded = reference_data.load_country_reference("  United Kingdom  ")
    ref_normal = reference_data.load_country_reference("United Kingdom")

    assert ref_lower is not None
    assert ref_padded is not None
    assert ref_lower.name == ref_normal.name == ref_padded.name


def test_unknown_country_returns_none_not_fabricated():
    ref = reference_data.load_country_reference("Atlantis")
    assert ref is None


def test_unknown_industry_returns_none_not_fabricated():
    ref = reference_data.load_industry_reference("Time Travel")
    assert ref is None


def test_empty_or_missing_name_returns_none():
    assert reference_data.load_country_reference("") is None
    assert reference_data.load_country_reference("   ") is None
    assert reference_data.load_industry_reference("") is None


def test_every_loaded_reference_carries_a_disclaimer():
    for name in reference_data.list_available_countries():
        ref = reference_data.load_country_reference(name)
        assert ref.source_note
        assert "job description" in ref.source_note.lower() or "general" in ref.source_note.lower()

    for name in reference_data.list_available_industries():
        ref = reference_data.load_industry_reference(name)
        assert ref.source_note
        assert "job description" in ref.source_note.lower() or "general" in ref.source_note.lower()
