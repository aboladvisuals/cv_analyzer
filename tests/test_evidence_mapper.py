"""
tests/test_evidence_mapper.py

Tests for evidence_mapper.py, built directly around the brief's own
example scenario:
  - SQL: required, frequency high, CV has it in Experience -> STRONG_MATCH
  - NHS employment: no direct match, but a project references NHS ->
    TRANSFERABLE, and CRUCIALLY never labelled as direct experience
  - Something genuinely absent from the CV -> MISSING, never invented

Uses the same fictional sample data as the other multi-JD tests.
"""

import config
import cv_parser
import job_parser
import similar_jobs
import frequency_analyser
import evidence_mapper
from config import EvidenceStatus


CV_PATH = config.SAMPLE_DATA_DIR / "sample_cv_jordan_ellis.txt"
TARGET_JD_PATH = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"
SIMILAR_JD_PATHS = [
    config.SAMPLE_DATA_DIR / "sample_jd_similar_1.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_2.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_3.txt",
]


def _build_matrix():
    cv_result = cv_parser.parse_cv(CV_PATH)
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in SIMILAR_JD_PATHS]

    sj_result = similar_jobs.analyse_similar_jobs(target_text, similar_texts)
    freq_result = frequency_analyser.analyse_frequency(sj_result)
    return evidence_mapper.build_evidence_matrix(cv_result, freq_result)


def test_sql_is_a_strong_match_from_experience():
    matrix = _build_matrix()
    row = matrix.row_for("SQL")

    assert row is not None
    assert row.evidence_status == EvidenceStatus.STRONG_MATCH
    assert row.cv_evidence_label == "YES"
    # Experience is preferred over Skills when both have evidence, since
    # it gives a distinct, meaningful snippet rather than a shared
    # whole-line dump from a comma-separated skills list.
    assert row.evidence_source == "experience"
    assert row.evidence_snippet != ""


def test_power_bi_is_a_strong_match():
    matrix = _build_matrix()
    row = matrix.row_for("Power BI")

    assert row.evidence_status == EvidenceStatus.STRONG_MATCH
    assert row.cv_evidence_label == "YES"


def test_nhs_experience_is_transferable_not_direct():
    matrix = _build_matrix()
    row = matrix.row_for("Healthcare/NHS data experience")

    assert row is not None
    # This is the core brief scenario: no direct NHS employment evidence,
    # but the CV's NHS A&E personal project provides transferable evidence.
    assert row.evidence_status == EvidenceStatus.TRANSFERABLE
    assert row.cv_evidence_label == "TRANSFERABLE"
    assert row.evidence_source == "projects"
    assert "nhs" in row.evidence_snippet.lower() or "a&e" in row.evidence_snippet.lower()
    # Critically: the gap note must not claim direct experience.
    assert "direct" in row.gap.lower()
    assert "not" in row.gap.lower() or "no" in row.gap.lower()


def test_transferable_evidence_is_never_mislabelled_as_strong_match():
    matrix = _build_matrix()
    row = matrix.row_for("Healthcare/NHS data experience")

    # Guard against a regression where transferable evidence gets silently
    # upgraded to a strong/direct match — that would misrepresent the
    # candidate.
    assert row.evidence_status != EvidenceStatus.STRONG_MATCH


def test_genuinely_missing_requirement_is_reported_as_missing_not_invented():
    matrix = _build_matrix()
    # "Attention to detail" only appears once across the similar JDs and
    # is not present anywhere in the sample CV text — a good genuine
    # "missing" case.
    row = matrix.row_for("Attention to detail")

    assert row is not None
    assert row.evidence_status == EvidenceStatus.MISSING
    assert row.cv_evidence_label == "NO"
    assert row.evidence_source == ""
    assert row.evidence_snippet == ""


def test_hyphenated_cv_wording_still_matches_spaced_phrase():
    # The sample CV says "data-quality issues" (hyphenated); the phrase
    # vocabulary is "data quality" (spaced). These must still match —
    # otherwise genuine evidence would be missed purely over punctuation.
    matrix = _build_matrix()
    row = matrix.row_for("Data quality")

    assert row is not None
    assert row.evidence_status in (EvidenceStatus.STRONG_MATCH, EvidenceStatus.PARTIAL_MATCH)
    assert row.cv_evidence_label != "NO"


def test_degree_evidence_recognised_from_bsc_wording():
    # The sample CV states "BSc Mathematics" rather than the literal
    # phrase "degree level" — the vocabulary should still recognise this
    # as evidence of degree-level education.
    matrix = _build_matrix()
    row = matrix.row_for("Degree-level education")

    assert row is not None
    assert row.cv_evidence_label != "NO"
    assert row.evidence_source == "education"


def test_every_row_carries_jd_frequency_and_gap_explanation():
    matrix = _build_matrix()
    assert matrix.rows  # matrix isn't empty
    for row in matrix.rows:
        assert row.jd_frequency  # e.g. "3/3", never blank
        assert row.gap != ""     # every row must explain itself


def test_skills_on_the_same_cv_line_get_distinct_snippets():
    # SQL, Excel, and Python all sit on the same comma-separated Skills
    # line in the sample CV. Each requirement's evidence snippet must be
    # distinct — not an identical whole-line dump shared by every skill,
    # which would make generated personal-statement sentences repetitive
    # and uninformative.
    matrix = _build_matrix()
    sql_row = matrix.row_for("SQL")
    excel_row = matrix.row_for("Excel")
    python_row = matrix.row_for("Python")

    snippets = {sql_row.evidence_snippet, excel_row.evidence_snippet, python_row.evidence_snippet}
    assert len(snippets) == 3  # all different, none sharing the whole-line snippet


def test_wrapped_bullet_line_is_not_truncated_mid_sentence():
    # The sample CV's SQL bullet wraps across two physical lines:
    #   "- Built and maintained SQL queries to support weekly reporting for three"
    #   "  internal teams."
    # The snippet must be the full, merged sentence — not cut off at
    # "for three" because that's where the raw text file happened to
    # wrap the line.
    matrix = _build_matrix()
    row = matrix.row_for("SQL")

    assert row.evidence_status == EvidenceStatus.STRONG_MATCH
    assert row.evidence_snippet.rstrip().endswith((".", "!", "?"))
    assert "internal teams" in row.evidence_snippet
    assert not row.evidence_snippet.rstrip().endswith("three")


def test_invalid_cv_produces_all_missing_rows_without_crashing():
    invalid_cv = cv_parser.parse_cv("")  # empty pasted text -> invalid

    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in SIMILAR_JD_PATHS]
    sj_result = similar_jobs.analyse_similar_jobs(target_text, similar_texts)
    freq_result = frequency_analyser.analyse_frequency(sj_result)

    matrix = evidence_mapper.build_evidence_matrix(invalid_cv, freq_result)

    assert matrix.rows
    assert all(r.evidence_status == EvidenceStatus.MISSING for r in matrix.rows)
