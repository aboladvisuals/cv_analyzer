"""
tests/test_personal_statement.py

Tests for personal_statement.py. Covers:
  - the hard rule: no MISSING/CONSIDER_DEVELOPING requirement ever
    appears in generated text, for any tier
  - MASTER tier selects recurring, evidence-backed requirements and
    carries the exact required limitation note
  - VACANCY tier prioritises the target JD's own required items
  - INDUSTRY tier requires an industry and surfaces industry-relevant
    evidence even below the Master frequency threshold
  - no banned generic-AI clichés appear in generated text
"""

import config
import cv_parser
import similar_jobs
import frequency_analyser
import evidence_mapper
import gap_analyser
import personal_statement
from config import StatementTier
from personal_statement import PersonalStatementInput


CV_PATH = config.SAMPLE_DATA_DIR / "sample_cv_jordan_ellis.txt"
TARGET_JD_PATH = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"
SIMILAR_JD_PATHS = [
    config.SAMPLE_DATA_DIR / "sample_jd_similar_1.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_2.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_3.txt",
]

BANNED_PHRASES = [
    "highly motivated",
    "team player",
    "results-driven",
    "hard-working individual",
    "passionate about",
]


def _build_gap_result():
    cv_result = cv_parser.parse_cv(CV_PATH)
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in SIMILAR_JD_PATHS]

    sj_result = similar_jobs.analyse_similar_jobs(target_text, similar_texts)
    freq_result = frequency_analyser.analyse_frequency(sj_result)
    matrix = evidence_mapper.build_evidence_matrix(cv_result, freq_result)
    return gap_analyser.analyse_gaps(matrix)


def test_master_statement_never_includes_missing_requirements():
    gap_result = _build_gap_result()
    genuine_gap_phrases = {e.requirement for e in gap_result.genuine_gaps}

    result = personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    )

    assert genuine_gap_phrases  # sanity check the test data has real gaps
    for phrase in result.included_requirements:
        assert phrase not in genuine_gap_phrases

    for phrase in genuine_gap_phrases:
        assert phrase not in result.statement_text


def test_vacancy_statement_never_includes_missing_requirements():
    gap_result = _build_gap_result()
    genuine_gap_phrases = {e.requirement for e in gap_result.genuine_gaps}

    result = personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.VACANCY)
    )

    for phrase in genuine_gap_phrases:
        assert phrase not in result.statement_text


def test_master_statement_carries_the_reusability_limitation_note():
    gap_result = _build_gap_result()

    result = personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    )

    assert result.limitation_note == personal_statement.MASTER_LIMITATION_NOTE
    assert "reuse" in result.limitation_note.lower()


def test_vacancy_statement_has_no_reusability_limitation_note():
    gap_result = _build_gap_result()

    result = personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.VACANCY)
    )

    assert result.limitation_note == ""


def test_vacancy_statement_prioritises_required_target_jd_items():
    gap_result = _build_gap_result()

    result = personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.VACANCY)
    )

    # SQL is REQUIRED in the target JD with strong evidence — it should
    # be included and should appear early (not buried at the end).
    assert "SQL" in result.included_requirements
    assert result.included_requirements.index("SQL") < 4


def test_industry_tier_requires_an_industry():
    gap_result = _build_gap_result()

    import pytest
    with pytest.raises(ValueError):
        personal_statement.generate_personal_statement(
            gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.INDUSTRY)
        )


def test_industry_tier_surfaces_healthcare_evidence():
    gap_result = _build_gap_result()

    result = personal_statement.generate_personal_statement(
        gap_result,
        PersonalStatementInput(
            target_role="Data Analyst", tier=StatementTier.INDUSTRY, industry="Healthcare"
        ),
    )

    # The NHS transferable evidence is industry-relevant even though its
    # cross-JD frequency alone wouldn't necessarily guarantee inclusion —
    # the industry tier should surface it specifically.
    assert "Healthcare/NHS data experience" in result.included_requirements
    assert "healthcare" in result.statement_text.lower()


def test_no_banned_generic_ai_cliches_in_any_tier():
    gap_result = _build_gap_result()

    for tier, kwargs in [
        (StatementTier.MASTER, {}),
        (StatementTier.VACANCY, {}),
        (StatementTier.INDUSTRY, {"industry": "Healthcare"}),
    ]:
        result = personal_statement.generate_personal_statement(
            gap_result,
            PersonalStatementInput(target_role="Data Analyst", tier=tier, **kwargs),
        )
        text_lower = result.statement_text.lower()
        for banned in BANNED_PHRASES:
            assert banned not in text_lower, f"'{banned}' found in {tier} statement"


def test_no_leaked_bullet_markers_in_generated_prose():
    # evidence_snippet may start with "- " (a CV bullet marker). That's
    # fine in a table row but must not leak into generated sentences —
    # e.g. "directly — - Designed a..." looks broken.
    gap_result = _build_gap_result()

    result = personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    )
    assert "— -" not in result.statement_text
    assert ": -" not in result.statement_text


def test_parenthetical_comma_is_not_split_mid_phrase():
    # The CV skills line contains "Python (pandas, basic)" — the comma
    # inside the parentheses must not be treated as a list separator,
    # which would otherwise truncate the snippet to "Python (pandas".
    gap_result = _build_gap_result()

    result = personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    )
    assert "(pandas." not in result.statement_text  # the broken, truncated form


def test_no_redundant_phrase_echo_when_snippet_already_starts_with_it():
    # The CV's Excel evidence snippet is literally "Excel (advanced)" —
    # the naive template would produce the awkward echo
    # "Excel: Excel (advanced)". That exact redundant pattern must not
    # appear in generated text.
    gap_result = _build_gap_result()

    result = personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    )
    assert "Excel: Excel" not in result.statement_text
    # Also guards against a stray mid-sentence period, e.g.
    # "Excel (advanced). as a skill" — the snippet's own trailing period
    # must not leak into the middle of the replacement sentence.
    assert ". as a skill" not in result.statement_text


def test_two_requirements_sharing_the_same_cv_bullet_are_not_both_elaborated():
    # "Dashboards" and "Power BI" both match the same CV Experience
    # bullet ("Designed a Power BI dashboard..."). Without deduplication,
    # the statement would describe that one bullet twice, almost
    # verbatim, as if it were two separate pieces of evidence — found by
    # actually reading a generated Vacancy-tier statement, not by a
    # passing test alone.
    gap_result = _build_gap_result()

    result = personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.VACANCY)
    )

    occurrences = result.statement_text.count("Designed a Power BI dashboard")
    assert occurrences <= 1, (
        f"The same CV bullet was elaborated on {occurrences} times in the body text — "
        f"should be deduplicated to at most once."
    )


def test_unknown_tier_raises_value_error():
    gap_result = _build_gap_result()

    import pytest
    with pytest.raises(ValueError):
        personal_statement.generate_personal_statement(
            gap_result, PersonalStatementInput(target_role="Data Analyst", tier="not_a_real_tier")
        )
