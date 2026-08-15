"""
tests/test_optimiser.py

Tests for optimiser.py. Covers:
  - NHS transferable evidence produces a concrete before/after suggestion
    that stays honest (doesn't claim direct employment)
  - a bare skills-list entry produces an advisory recommendation (no
    fabricated wording)
  - genuine gaps (no CV evidence at all) NEVER produce a suggestion or
    recommendation — only appear in unaddressed_gaps
  - nothing is ever auto-approved
"""

import config
import cv_parser
import similar_jobs
import frequency_analyser
import evidence_mapper
import gap_analyser
import optimiser
from config import EvidenceStatus


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


def test_transferable_evidence_produces_a_concrete_suggestion():
    gap_result = _build_gap_result()
    result = optimiser.generate_optimisation_suggestions(gap_result)

    nhs_suggestion = next(
        (s for s in result.suggestions if s.requirement == "Healthcare/NHS data experience"), None
    )
    assert nhs_suggestion is not None
    assert nhs_suggestion.original_wording  # original text preserved verbatim
    assert nhs_suggestion.original_wording in nhs_suggestion.proposed_wording
    assert nhs_suggestion.reason


def test_transferable_suggestion_never_claims_direct_employment():
    gap_result = _build_gap_result()
    result = optimiser.generate_optimisation_suggestions(gap_result)

    nhs_suggestion = next(
        s for s in result.suggestions if s.requirement == "Healthcare/NHS data experience"
    )
    proposed_lower = nhs_suggestion.proposed_wording.lower()
    assert "project" in proposed_lower or "personal project" in nhs_suggestion.original_wording.lower()
    assert "employed" not in proposed_lower
    assert "worked at nhs" not in proposed_lower


def test_bare_skills_list_entry_gets_advisory_recommendation_not_wording():
    gap_result = _build_gap_result()
    result = optimiser.generate_optimisation_suggestions(gap_result)

    # Excel's evidence is sourced from "skills" (a bare list entry) in
    # the sample CV — this should produce an advisory recommendation,
    # not a fabricated before/after wording change.
    excel_entries = [r for r in result.recommendations if r.requirement == "Excel"]
    assert excel_entries
    assert not any(s.requirement == "Excel" for s in result.suggestions)


def test_genuine_gaps_never_produce_suggestions_or_recommendations():
    gap_result = _build_gap_result()
    genuine_gap_phrases = {e.requirement for e in gap_result.genuine_gaps}
    assert genuine_gap_phrases  # sanity check

    result = optimiser.generate_optimisation_suggestions(gap_result)

    suggestion_phrases = {s.requirement for s in result.suggestions}
    recommendation_phrases = {r.requirement for r in result.recommendations}

    assert genuine_gap_phrases.isdisjoint(suggestion_phrases)
    assert genuine_gap_phrases.isdisjoint(recommendation_phrases)
    assert genuine_gap_phrases <= set(result.unaddressed_gaps)


def test_nothing_is_auto_approved():
    gap_result = _build_gap_result()
    result = optimiser.generate_optimisation_suggestions(gap_result)

    assert result.suggestions  # sanity check there's something to approve
    for suggestion in result.suggestions:
        assert suggestion.approved is None
    assert result.approved_suggestions() == []


def test_approving_a_suggestion_makes_it_appear_in_approved_list():
    gap_result = _build_gap_result()
    result = optimiser.generate_optimisation_suggestions(gap_result)

    result.suggestions[0].approved = True
    approved = result.approved_suggestions()

    assert len(approved) == 1
    assert approved[0] is result.suggestions[0]


def test_disclaimer_is_present_and_warns_against_untrue_additions():
    gap_result = _build_gap_result()
    result = optimiser.generate_optimisation_suggestions(gap_result)

    assert "genuinely true" in result.disclaimer.lower()
    assert "automatically" in result.disclaimer.lower()


def test_evidence_without_a_number_gets_a_quantification_recommendation():
    # The sample CV's SQL evidence ("...for three internal teams") has no
    # literal digit — the spelled-out "three" is a known, accepted
    # limitation of the simple digit-based detector.
    gap_result = _build_gap_result()
    result = optimiser.generate_optimisation_suggestions(gap_result)

    sql_quant_recs = [
        r for r in result.recommendations
        if r.requirement == "SQL" and "measurable outcome" in r.advice.lower()
    ]
    assert sql_quant_recs


def test_evidence_with_a_real_number_gets_no_quantification_recommendation():
    import gap_analyser

    entry = gap_analyser.GapAnalysisEntry(
        requirement="SQL",
        jd_frequency="3/3",
        target_jd_category="required",
        evidence_status="strong_match",
        evidence_source="experience",
        evidence_snippet="Reduced report generation time by 40% using optimised SQL queries.",
        message_type="has_skill",
        message="You have direct evidence of SQL in your experience section.",
        priority="none",
    )
    gap_result = gap_analyser.GapAnalysisResult(entries=[entry])

    result = optimiser.generate_optimisation_suggestions(gap_result)

    quant_recs = [r for r in result.recommendations if "measurable outcome" in r.advice.lower()]
    assert quant_recs == []


def test_transferable_evidence_without_a_number_also_gets_the_nudge():
    # The NHS A&E project snippet has no digit either — the nudge should
    # apply to transferable evidence, not just direct skill matches.
    gap_result = _build_gap_result()
    result = optimiser.generate_optimisation_suggestions(gap_result)

    nhs_quant_recs = [
        r for r in result.recommendations
        if r.requirement == "Healthcare/NHS data experience" and "measurable outcome" in r.advice.lower()
    ]
    assert nhs_quant_recs
