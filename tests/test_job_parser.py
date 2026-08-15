"""
tests/test_job_parser.py

Tests for job_parser.py. Covers:
  - parsing the sample target job description and correctly categorising
    requirements as required / preferred / responsibility / competency
  - empty job description text
  - text with no recognisable section headers (should parse without
    crashing, just with zero requirements)
"""

import config
import job_parser
from config import RequirementCategory


SAMPLE_JD_PATH = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"


def test_parses_sample_jd_and_categorises_requirements():
    text = SAMPLE_JD_PATH.read_text(encoding="utf-8")
    result = job_parser.parse_job_description(text)

    assert result.is_valid
    assert len(result.requirements) > 0

    required_texts = [r.text for r in result.by_category(RequirementCategory.REQUIRED)]
    preferred_texts = [r.text for r in result.by_category(RequirementCategory.PREFERRED)]
    responsibility_texts = [r.text for r in result.by_category(RequirementCategory.RESPONSIBILITY)]
    competency_texts = [r.text for r in result.by_category(RequirementCategory.COMPETENCY)]

    assert any("SQL" in t for t in required_texts)
    assert any("Excel" in t for t in required_texts)

    assert any("Python" in t for t in preferred_texts)
    assert any("NHS" in t for t in preferred_texts)

    assert any("performance" in t.lower() for t in responsibility_texts)

    assert any("teamwork" in t.lower() or "collaboration" in t.lower() for t in competency_texts)


def test_every_requirement_keeps_its_source_line_for_traceability():
    text = SAMPLE_JD_PATH.read_text(encoding="utf-8")
    result = job_parser.parse_job_description(text)

    for requirement in result.requirements:
        assert requirement.source_line != ""
        # The cleaned requirement text should be a substring of (or equal
        # to) its own source line — proving we didn't invent content that
        # wasn't in the original job description.
        assert requirement.text in requirement.source_line or requirement.text == requirement.source_line


def test_empty_job_description_is_invalid():
    result = job_parser.parse_job_description("")

    assert not result.is_valid
    assert result.error != ""


def test_unstructured_text_parses_without_crashing_but_finds_nothing():
    text = "We are a great company. Come work with us! No structured sections here."
    result = job_parser.parse_job_description(text)

    assert result.is_valid
    assert result.requirements == []
