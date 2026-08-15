"""
tests/test_report_generator.py

Tests for report_generator.py. Covers:
  - build_report_content() assembles the right sections from real
    analysis data (pure logic, fully testable)
  - optional sections (statement, optimisation) only appear when provided
  - write_docx_report() and write_pdf_report() produce real, non-empty
    files (a full pixel-level render check isn't practical in a test
    suite, but "the file exists, is non-trivial in size, and has the
    right extension" catches the most likely failure modes — a crash,
    or a silently empty file)
"""

import config
import cv_parser
import similar_jobs
import frequency_analyser
import evidence_mapper
import gap_analyser
import personal_statement
import statement_quality
import optimiser
import app
import report_generator
from config import StatementTier


CV_PATH = config.SAMPLE_DATA_DIR / "sample_cv_jordan_ellis.txt"
TARGET_JD_PATH = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"
SIMILAR_JD_PATHS = [
    config.SAMPLE_DATA_DIR / "sample_jd_similar_1.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_2.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_3.txt",
]


def _build_bundle():
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in SIMILAR_JD_PATHS]
    return app.run_analysis(str(CV_PATH), target_text, similar_texts)


def test_content_model_has_core_sections_without_statement_or_optimisation():
    bundle = _build_bundle()
    content = report_generator.build_report_content(bundle, target_role="Data Analyst")

    headings = [s.heading for s in content.sections]
    assert "CV Overview" in headings
    assert "Job Description Analysis" in headings
    assert "Evidence Matrix" in headings
    assert "Gap Analysis Summary" in headings
    # Optional sections must NOT appear when not provided.
    assert not any("Personal Statement" in h for h in headings)
    assert "CV Optimisation Suggestions" not in headings


def test_content_model_includes_statement_section_when_provided():
    bundle = _build_bundle()
    stmt_result, quality_result = app.generate_statement_package(
        bundle.gap_result, target_role="Data Analyst", tier=StatementTier.MASTER
    )
    content = report_generator.build_report_content(
        bundle, target_role="Data Analyst", stmt_result=stmt_result, quality_result=quality_result
    )

    headings = [s.heading for s in content.sections]
    assert "Personal Statement (Master)" in headings
    statement_section = next(s for s in content.sections if s.heading == "Personal Statement (Master)")
    assert any("Coverage" in p for p in statement_section.paragraphs)


def test_content_model_includes_optimisation_section_when_provided():
    bundle = _build_bundle()
    optimisation_result = optimiser.generate_optimisation_suggestions(bundle.gap_result)
    content = report_generator.build_report_content(
        bundle, target_role="Data Analyst", optimisation_result=optimisation_result
    )

    headings = [s.heading for s in content.sections]
    assert "CV Optimisation Suggestions" in headings
    opt_section = next(s for s in content.sections if s.heading == "CV Optimisation Suggestions")
    assert any("Healthcare/NHS data experience" in p for p in opt_section.paragraphs)


def test_content_model_includes_country_industry_context_when_provided():
    bundle = _build_bundle()
    content = report_generator.build_report_content(
        bundle, target_role="Data Analyst", country="United Kingdom", industry="Healthcare"
    )

    headings = [s.heading for s in content.sections]
    assert "Country & Industry Context" in headings
    context_section = next(s for s in content.sections if s.heading == "Country & Industry Context")
    assert any("United Kingdom" in p for p in context_section.paragraphs)
    assert any("Healthcare" in p for p in context_section.paragraphs)
    # The "job description is primary" caveat must always be present.
    assert any("job description" in p.lower() for p in context_section.paragraphs)


def test_content_model_omits_context_section_when_neither_provided():
    bundle = _build_bundle()
    content = report_generator.build_report_content(bundle, target_role="Data Analyst")

    headings = [s.heading for s in content.sections]
    assert "Country & Industry Context" not in headings


def test_content_model_omits_context_section_for_unknown_country():
    bundle = _build_bundle()
    content = report_generator.build_report_content(
        bundle, target_role="Data Analyst", country="Narnia"
    )

    headings = [s.heading for s in content.sections]
    assert "Country & Industry Context" not in headings


def test_evidence_matrix_table_matches_matrix_row_count():
    bundle = _build_bundle()
    content = report_generator.build_report_content(bundle, target_role="Data Analyst")

    matrix_section = next(s for s in content.sections if s.heading == "Evidence Matrix")
    assert matrix_section.table is not None
    assert len(matrix_section.table.rows) == len(bundle.evidence_matrix.rows)
    assert matrix_section.table.headers == [
        "Requirement", "JD Frequency", "Target JD", "CV Evidence", "Source"
    ]


def test_write_docx_report_produces_a_real_file(tmp_path):
    bundle = _build_bundle()
    content = report_generator.build_report_content(bundle, target_role="Data Analyst")
    output_path = tmp_path / "report.docx"

    result_path = report_generator.write_docx_report(content, output_path)

    assert result_path.exists()
    assert result_path.suffix == ".docx"
    assert result_path.stat().st_size > 1000  # a real docx, not an empty stub


def test_write_pdf_report_produces_a_real_file(tmp_path):
    bundle = _build_bundle()
    content = report_generator.build_report_content(bundle, target_role="Data Analyst")
    output_path = tmp_path / "report.pdf"

    result_path = report_generator.write_pdf_report(content, output_path)

    assert result_path.exists()
    assert result_path.suffix == ".pdf"
    assert result_path.stat().st_size > 1000
    with open(result_path, "rb") as f:
        assert f.read(5) == b"%PDF-"  # a genuine PDF file signature


def test_write_docx_report_with_full_package(tmp_path):
    # End-to-end: CV + JD analysis + statement + optimisation, all in one
    # report — the most complete real-world case.
    bundle = _build_bundle()
    stmt_result, quality_result = app.generate_statement_package(
        bundle.gap_result, target_role="Data Analyst", tier=StatementTier.VACANCY,
        organisation="Northtown NHS Foundation Trust",
    )
    optimisation_result = optimiser.generate_optimisation_suggestions(bundle.gap_result)
    content = report_generator.build_report_content(
        bundle,
        target_role="Data Analyst",
        stmt_result=stmt_result,
        quality_result=quality_result,
        optimisation_result=optimisation_result,
    )

    output_path = tmp_path / "full_report.docx"
    result_path = report_generator.write_docx_report(content, output_path)

    assert result_path.exists()
    assert result_path.stat().st_size > 1000
