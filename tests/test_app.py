"""
tests/test_app.py

Tests for app.py's orchestration functions ONLY — run_analysis() and
generate_statement_package(). These are pure functions with no
input()/print() calls, so they can be tested directly like every other
module. The interactive CLI (menus, prompts) is not unit tested — that's
a deliberate, standard limitation of CLI testing, not an oversight; the
logic those prompts call into is what's actually tested here.
"""

import config
import app
from config import StatementTier


CV_PATH = config.SAMPLE_DATA_DIR / "sample_cv_jordan_ellis.txt"
TARGET_JD_PATH = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"
SIMILAR_JD_PATHS = [
    config.SAMPLE_DATA_DIR / "sample_jd_similar_1.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_2.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_3.txt",
]


def test_run_analysis_full_pipeline_with_similar_jds():
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in SIMILAR_JD_PATHS]

    bundle = app.run_analysis(str(CV_PATH), target_text, similar_texts)

    assert bundle.cv_result.is_valid
    assert bundle.similar_jobs_result.similar_jds_parsed == 3
    assert bundle.frequency_result.entries
    assert bundle.evidence_matrix.rows
    assert bundle.gap_result.entries
    # Same end-to-end guarantee validated in earlier modules should still
    # hold when driven through the app-level orchestration function.
    sql_entry = next(e for e in bundle.gap_result.entries if e.requirement == "SQL")
    assert sql_entry.message_type == "has_skill"


def test_run_analysis_with_no_similar_jds_still_works():
    # This is what powers "Analyse CV + target job" mode (no similar JDs
    # at all) — the pipeline must still produce a valid, usable result.
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")

    bundle = app.run_analysis(str(CV_PATH), target_text, similar_jd_texts=[])

    assert bundle.cv_result.is_valid
    assert bundle.similar_jobs_result.similar_jds_parsed == 0
    assert bundle.gap_result.entries  # target-JD-only requirements still classified
    sql_entry = next(e for e in bundle.gap_result.entries if e.requirement == "SQL")
    assert sql_entry.jd_frequency == "0/0"


def test_run_analysis_with_invalid_cv_does_not_crash():
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")

    bundle = app.run_analysis("", target_text, similar_jd_texts=[])

    assert not bundle.cv_result.is_valid
    # Downstream stages must still run cleanly rather than raising.
    assert bundle.gap_result.entries
    assert all(e.evidence_status == "missing" for e in bundle.gap_result.entries)


def test_generate_statement_package_end_to_end():
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in SIMILAR_JD_PATHS]
    bundle = app.run_analysis(str(CV_PATH), target_text, similar_texts)

    stmt_result, quality_result = app.generate_statement_package(
        bundle.gap_result, target_role="Data Analyst", tier=StatementTier.MASTER
    )

    assert stmt_result.statement_text
    assert stmt_result.included_requirements
    assert 0.0 <= quality_result.coverage_score <= 1.0
    assert len(quality_result.checklist) == 13


def test_generate_statement_package_vacancy_tier_with_organisation():
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in SIMILAR_JD_PATHS]
    bundle = app.run_analysis(str(CV_PATH), target_text, similar_texts)

    stmt_result, quality_result = app.generate_statement_package(
        bundle.gap_result,
        target_role="Data Analyst",
        tier=StatementTier.VACANCY,
        organisation="Northtown NHS Foundation Trust",
    )

    assert "Northtown NHS Foundation Trust" in stmt_result.statement_text
