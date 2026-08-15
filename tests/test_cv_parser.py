"""
tests/test_cv_parser.py

Tests for cv_parser.py. Covers:
  - parsing a plain-text sample CV and detecting its sections
  - parsing pasted CV text (no file at all)
  - parsing a DOCX CV (built on the fly, so we don't need a binary fixture)
  - empty file handling
  - unsupported file type handling
  - missing file handling
"""

from pathlib import Path

import pytest

import cv_parser
import config


SAMPLE_CV_PATH = config.SAMPLE_DATA_DIR / "sample_cv_jordan_ellis.txt"


def test_parses_sample_txt_cv_and_detects_sections():
    result = cv_parser.parse_cv(SAMPLE_CV_PATH)

    assert result.is_valid
    assert result.source_format == "txt"
    assert "SQL" in result.raw_text

    # We don't assert exact wording (that's brittle) — just that the
    # sections we know exist in the sample CV were actually detected.
    assert result.section("skills") != ""
    assert "SQL" in result.section("skills")
    assert result.section("experience") != ""
    assert "GreenTech" in result.section("experience")
    assert result.section("education") != ""
    assert result.section("certifications") != ""
    assert result.section("projects") != ""
    assert "NHS A&E" in result.section("projects")


def test_parses_pasted_cv_text():
    pasted = (
        "Summary\n"
        "A short professional summary.\n\n"
        "Skills\n"
        "SQL, Excel, Power BI\n\n"
        "Experience\n"
        "Data Analyst, Example Co (2022-Present)\n"
        "- Did analyst things.\n"
    )

    result = cv_parser.parse_cv(pasted)

    assert result.is_valid
    assert result.source_format == "pasted"
    assert "SQL" in result.section("skills")
    assert "Example Co" in result.section("experience")


def test_parses_docx_cv(tmp_path: Path):
    docx = pytest.importorskip("docx")

    doc = docx.Document()
    doc.add_paragraph("Summary")
    doc.add_paragraph("Analyst with SQL and Power BI experience.")
    doc.add_paragraph("Skills")
    doc.add_paragraph("SQL, Power BI, Excel")

    docx_path = tmp_path / "sample.docx"
    doc.save(str(docx_path))

    result = cv_parser.parse_cv(docx_path)

    assert result.is_valid
    assert result.source_format == "docx"
    assert "SQL" in result.section("skills")


def test_empty_file_returns_invalid_result(tmp_path: Path):
    empty_path = tmp_path / "empty.txt"
    empty_path.write_text("")

    result = cv_parser.parse_cv(empty_path)

    assert not result.is_valid
    assert result.error != ""


def test_unsupported_file_type_returns_invalid_result(tmp_path: Path):
    bad_path = tmp_path / "cv.xyz"
    bad_path.write_text("some content")

    result = cv_parser.parse_cv(bad_path)

    assert not result.is_valid
    assert "Unsupported file type" in result.error


def test_missing_file_returns_invalid_result(tmp_path: Path):
    missing_path = tmp_path / "does_not_exist.pdf"

    result = cv_parser.parse_cv(missing_path)

    assert not result.is_valid
    assert "not found" in result.error.lower()
