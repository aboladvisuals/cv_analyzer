"""
tests/test_gap_analyser.py

Tests for gap_analyser.py. Covers:
  - the four message types map correctly and exhaustively from evidence
    status (the core "never blur has-skill / transferable / missing"
    requirement from the brief)
  - priority is driven by the TARGET JD's own framing, not frequency
  - the SQL / NHS scenario from earlier phases produces the right
    end-to-end classification
"""

import config
import cv_parser
import similar_jobs
import frequency_analyser
import evidence_mapper
import gap_analyser
from config import EvidenceStatus, RequirementCategory, GapPriority
from gap_analyser import GapMessageType


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


def test_sql_is_classified_as_has_skill():
    result = _build_gap_result()
    entry = next(e for e in result.entries if e.requirement == "SQL")

    assert entry.message_type == GapMessageType.HAS_SKILL
    assert entry.priority == GapPriority.NONE
    assert "direct evidence" in entry.message.lower()


def test_nhs_experience_is_classified_as_transferable_not_has_skill():
    result = _build_gap_result()
    entry = next(
        e for e in result.entries if e.requirement == "Healthcare/NHS data experience"
    )

    assert entry.message_type == GapMessageType.TRANSFERABLE_EVIDENCE
    assert entry.message_type != GapMessageType.HAS_SKILL
    assert "not" in entry.message.lower() or "don't have direct" in entry.message.lower()


def test_missing_requirement_is_never_labelled_has_skill():
    result = _build_gap_result()
    missing_entries = [
        e for e in result.entries if e.evidence_status == EvidenceStatus.MISSING
    ]

    assert missing_entries  # sanity check there's at least one
    for entry in missing_entries:
        assert entry.message_type == GapMessageType.CONSIDER_DEVELOPING
        assert entry.message_type != GapMessageType.HAS_SKILL
        assert entry.message_type != GapMessageType.TRANSFERABLE_EVIDENCE


def test_message_type_mapping_is_exhaustive_and_one_to_one():
    """
    Every EvidenceStatus value must map to exactly one GapMessageType,
    and no two statuses should collapse into the same message type in a
    way that blurs the has-skill/transferable/missing distinction.
    """
    result = _build_gap_result()
    seen_mappings: dict[str, str] = {}

    for entry in result.entries:
        if entry.evidence_status in seen_mappings:
            assert seen_mappings[entry.evidence_status] == entry.message_type
        else:
            seen_mappings[entry.evidence_status] = entry.message_type

    # The three core statuses must map to three DIFFERENT message types.
    assert seen_mappings.get(EvidenceStatus.STRONG_MATCH) == GapMessageType.HAS_SKILL
    assert seen_mappings.get(EvidenceStatus.TRANSFERABLE) == GapMessageType.TRANSFERABLE_EVIDENCE
    assert seen_mappings.get(EvidenceStatus.MISSING) == GapMessageType.CONSIDER_DEVELOPING
    types = {
        seen_mappings.get(EvidenceStatus.STRONG_MATCH),
        seen_mappings.get(EvidenceStatus.TRANSFERABLE),
        seen_mappings.get(EvidenceStatus.MISSING),
    }
    assert len(types) == 3  # all distinct, nothing collapsed together


def test_required_and_missing_is_high_priority():
    result = _build_gap_result()
    # Degree-level education is REQUIRED in the target JD; if a case in
    # the matrix is required + missing, it must be HIGH priority. We
    # search rather than hard-code a specific requirement, since the
    # exact evidence outcome could shift as vocabulary is extended.
    required_missing = [
        e for e in result.entries
        if e.target_jd_category == RequirementCategory.REQUIRED
        and e.evidence_status == EvidenceStatus.MISSING
    ]
    for entry in required_missing:
        assert entry.priority == GapPriority.HIGH


def test_priority_is_not_derived_from_frequency():
    """
    Guards against priority logic accidentally keying off jd_frequency —
    two entries with the same target_jd_category and evidence_status
    must get the same priority regardless of how their frequencies differ.
    """
    result = _build_gap_result()
    priority_by_category_and_status: dict[tuple, set] = {}

    for entry in result.entries:
        key = (entry.target_jd_category, entry.evidence_status)
        priority_by_category_and_status.setdefault(key, set()).add(entry.priority)

    for key, priorities in priority_by_category_and_status.items():
        assert len(priorities) == 1, (
            f"Entries with the same (category, status)={key} got different "
            f"priorities {priorities} — priority must not vary by frequency."
        )


def test_result_grouping_helpers_are_consistent_with_entries():
    result = _build_gap_result()

    assert all(sm in result.entries for sm in result.strong_matches)
    assert all(e.message_type == GapMessageType.HAS_SKILL for e in result.strong_matches)
    assert all(e.message_type == GapMessageType.TRANSFERABLE_EVIDENCE for e in result.transferable)
    assert all(e.message_type == GapMessageType.CONSIDER_DEVELOPING for e in result.genuine_gaps)
    assert all(e.priority == GapPriority.HIGH for e in result.high_priority_gaps)
