"""
tests/test_statement_quality.py

Tests for statement_quality.py. Covers:
  - all four scores stay within 0.0-1.0
  - the required disclaimer is present and never omitted
  - a genuinely clean statement (built from earlier phases) passes the
    core checks
  - a DELIBERATELY fabricated statement fails "no fabricated experience"
    — proving the check can actually catch a real problem, not just
    always report success
"""

import config
import cv_parser
import similar_jobs
import frequency_analyser
import evidence_mapper
import gap_analyser
import personal_statement
import statement_quality
from config import StatementTier
from personal_statement import PersonalStatementInput, PersonalStatementResult


CV_PATH = config.SAMPLE_DATA_DIR / "sample_cv_jordan_ellis.txt"
TARGET_JD_PATH = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"
SIMILAR_JD_PATHS = [
    config.SAMPLE_DATA_DIR / "sample_jd_similar_1.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_2.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_3.txt",
]


def _build_gap_result():
    cv_result = cv_parser.parse_cv(CV_PATH)
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in SIMILAR_JD_PATHS]

    sj_result = similar_jobs.analyse_similar_jobs(target_text, similar_texts)
    freq_result = frequency_analyser.analyse_frequency(sj_result)
    matrix = evidence_mapper.build_evidence_matrix(cv_result, freq_result)
    return gap_analyser.analyse_gaps(matrix)


def test_scores_stay_within_zero_to_one():
    gap_result = _build_gap_result()
    stmt_input = PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    stmt_result = personal_statement.generate_personal_statement(gap_result, stmt_input)

    quality = statement_quality.check_statement_quality(gap_result, stmt_result, stmt_input)

    for score in (
        quality.coverage_score,
        quality.evidence_score,
        quality.keyword_relevance_score,
        quality.natural_language_score,
    ):
        assert 0.0 <= score <= 1.0


def test_disclaimer_is_always_present_and_not_a_guarantee():
    gap_result = _build_gap_result()
    stmt_input = PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    stmt_result = personal_statement.generate_personal_statement(gap_result, stmt_input)

    quality = statement_quality.check_statement_quality(gap_result, stmt_result, stmt_input)

    assert quality.summary_note == statement_quality.QUALITY_DISCLAIMER
    assert "not a guarantee" in quality.summary_note.lower()


def test_clean_master_statement_passes_core_checks():
    gap_result = _build_gap_result()
    stmt_input = PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    stmt_result = personal_statement.generate_personal_statement(gap_result, stmt_input)

    quality = statement_quality.check_statement_quality(gap_result, stmt_result, stmt_input)

    by_label = {item.label: item for item in quality.checklist}
    assert by_label["No fabricated experience"].passed
    assert by_label["No unsupported qualifications"].passed
    assert by_label["Uses genuine candidate evidence"].passed
    assert by_label["Relevant to target role"].passed
    assert by_label["Clear structure"].passed


def test_single_letter_genuine_gap_does_not_false_positive_on_fabrication():
    """
    Regression test for a real bug found during development: the sample
    data's genuine gaps include the single-letter requirement "R". A
    naive substring check ("r" in text) would match almost any English
    sentence containing the letter r, wrongly flagging every clean
    statement as fabricated. The check must use word-boundary matching.
    """
    gap_result = _build_gap_result()
    genuine_gap_phrases = {e.requirement for e in gap_result.genuine_gaps}
    assert "R" in genuine_gap_phrases  # sanity check the scenario still applies

    stmt_input = PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    stmt_result = personal_statement.generate_personal_statement(gap_result, stmt_input)

    quality = statement_quality.check_statement_quality(gap_result, stmt_result, stmt_input)

    by_label = {item.label: item for item in quality.checklist}
    assert by_label["No fabricated experience"].passed


def test_checklist_has_all_thirteen_items():
    gap_result = _build_gap_result()
    stmt_input = PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.VACANCY)
    stmt_result = personal_statement.generate_personal_statement(gap_result, stmt_input)

    quality = statement_quality.check_statement_quality(gap_result, stmt_result, stmt_input)

    assert len(quality.checklist) == 13


def test_fabricated_statement_fails_no_fabrication_check():
    """
    Deliberately construct a statement whose text claims a requirement
    the candidate has NO evidence for (a genuine gap). This proves the
    "no fabricated experience" check can actually fail — not just always
    report success on whatever the generator happens to produce.
    """
    gap_result = _build_gap_result()
    genuine_gap = gap_result.genuine_gaps[0]  # a requirement with zero evidence

    stmt_input = PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    fabricated_text = (
        f"I am a Data Analyst with strong experience in {genuine_gap.requirement}, "
        f"which I have used extensively in my career."
    )
    fabricated_result = PersonalStatementResult(
        tier=StatementTier.MASTER,
        statement_text=fabricated_text,
        included_requirements=[genuine_gap.requirement],  # falsely claims coverage
        excluded_requirements=[],
        limitation_note="",
        word_count=len(fabricated_text.split()),
    )

    quality = statement_quality.check_statement_quality(gap_result, fabricated_result, stmt_input)

    by_label = {item.label: item for item in quality.checklist}
    assert not by_label["No fabricated experience"].passed
    assert not by_label["No unsupported qualifications"].passed
    assert not quality.all_checks_passed


def test_keyword_stuffed_statement_scores_lower_on_keyword_relevance():
    """
    A statement that repeats the same requirement phrase many times
    should score noticeably lower on keyword relevance than one that
    mentions it once, naturally.
    """
    gap_result = _build_gap_result()
    stmt_input = PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)

    stuffed_text = "SQL SQL SQL is a skill I use. I love SQL. SQL SQL SQL SQL."
    stuffed_result = PersonalStatementResult(
        tier=StatementTier.MASTER,
        statement_text=stuffed_text,
        included_requirements=["SQL"],
        excluded_requirements=[],
        limitation_note="",
        word_count=len(stuffed_text.split()),
    )

    quality = statement_quality.check_statement_quality(gap_result, stuffed_result, stmt_input)

    assert quality.keyword_relevance_score < 0.5
