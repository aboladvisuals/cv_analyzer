"""
tests/test_ai_phrasing.py

Tests for ai_phrasing.py. No real network calls are made — _call_ai_api
is replaced with a fake via unittest.mock.patch in every test that would
otherwise reach it. Covers:
  - is_ai_available() logic (both AI_ENABLED and AI_API_KEY required)
  - polish_statement() falls back to the original text when AI isn't
    configured, at all, with a clear reason
  - a genuinely successful AI response is accepted
  - THE CRITICAL CASE: an AI response that mentions a genuine-gap
    requirement (something with zero CV evidence) is REJECTED, and the
    original rule-based text is used instead
  - a failed network call falls back gracefully rather than crashing
  - a degenerate (empty / wildly different length) response is rejected
"""

from unittest.mock import patch

import config
import cv_parser
import similar_jobs
import frequency_analyser
import evidence_mapper
import gap_analyser
import personal_statement
import ai_phrasing
from config import StatementTier
from personal_statement import PersonalStatementInput


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


def _build_statement(gap_result):
    return personal_statement.generate_personal_statement(
        gap_result, PersonalStatementInput(target_role="Data Analyst", tier=StatementTier.MASTER)
    )


def test_is_ai_available_requires_both_enabled_and_key(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", False)
    monkeypatch.setattr(config, "AI_API_KEY", "some-key")
    assert not ai_phrasing.is_ai_available()

    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "")
    assert not ai_phrasing.is_ai_available()

    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "some-key")
    assert ai_phrasing.is_ai_available()


def test_polish_statement_falls_back_when_ai_not_configured(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", False)
    gap_result = _build_gap_result()
    stmt_result = _build_statement(gap_result)

    result = ai_phrasing.polish_statement(stmt_result, gap_result)

    assert not result.used_ai
    assert result.polished_text == result.original_text == stmt_result.statement_text
    assert "not configured" in result.error.lower()


def test_polish_statement_accepts_a_genuine_rephrasing(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "fake-key-for-test")
    gap_result = _build_gap_result()
    stmt_result = _build_statement(gap_result)

    # A fake "polished" response that's just a lightly reworded version
    # of the same length, with no new content.
    fake_response = " ".join(stmt_result.statement_text.split())  # same words, reflowed

    with patch("ai_phrasing._call_ai_api", return_value=fake_response):
        result = ai_phrasing.polish_statement(stmt_result, gap_result)

    assert result.used_ai
    assert result.polished_text == fake_response
    assert result.error == ""


def test_fabricated_ai_response_is_rejected_and_falls_back(monkeypatch):
    """
    THE CRITICAL TEST: if the AI response mentions a requirement the
    candidate has NO genuine evidence for, it must be rejected — not
    silently passed through to the user.
    """
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "fake-key-for-test")
    gap_result = _build_gap_result()
    stmt_result = _build_statement(gap_result)

    genuine_gap = gap_result.genuine_gaps[0]  # e.g. "R" or "Teamwork" — zero CV evidence
    fabricated_response = (
        f"I am a Data Analyst with strong, extensive experience in "
        f"{genuine_gap.requirement}, which I have used throughout my career. "
        + " ".join(stmt_result.statement_text.split())  # padded to a plausible length
    )

    with patch("ai_phrasing._call_ai_api", return_value=fabricated_response):
        result = ai_phrasing.polish_statement(stmt_result, gap_result)

    assert not result.used_ai
    assert result.polished_text == stmt_result.statement_text  # original text used instead
    assert genuine_gap.requirement.lower() in result.error.lower() or "safety check" in result.error.lower()


def test_network_failure_falls_back_gracefully(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "fake-key-for-test")
    gap_result = _build_gap_result()
    stmt_result = _build_statement(gap_result)

    with patch("ai_phrasing._call_ai_api", side_effect=ConnectionError("network unreachable")):
        result = ai_phrasing.polish_statement(stmt_result, gap_result)

    assert not result.used_ai
    assert result.polished_text == stmt_result.statement_text
    assert "request failed" in result.error.lower()


def test_empty_ai_response_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "fake-key-for-test")
    gap_result = _build_gap_result()
    stmt_result = _build_statement(gap_result)

    with patch("ai_phrasing._call_ai_api", return_value="   "):
        result = ai_phrasing.polish_statement(stmt_result, gap_result)

    assert not result.used_ai
    assert result.polished_text == stmt_result.statement_text


def test_drastically_shorter_ai_response_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "fake-key-for-test")
    gap_result = _build_gap_result()
    stmt_result = _build_statement(gap_result)

    with patch("ai_phrasing._call_ai_api", return_value="Very short reply."):
        result = ai_phrasing.polish_statement(stmt_result, gap_result)

    assert not result.used_ai
    assert "length changed" in result.error.lower()
