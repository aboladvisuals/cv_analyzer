"""
gap_analyser.py

Takes the Evidence Matrix from evidence_mapper.py and turns each row into
a plain-language classification and message — while enforcing the
brief's core rule at the code level, not just in wording:

    "Candidate has this skill"
        MUST be a different message type from
    "Candidate should consider developing this skill"
        MUST be a different message type from
    "Candidate has transferable evidence"

These three (plus a fourth: "evidence exists but may need strengthening")
are modelled as GapMessageType — a closed set of four values. There is no
code path that can produce a "has this skill" message from evidence that
was actually MISSING or TRANSFERABLE; the message type is derived
directly and only from evidence_status (see _message_type_for_status).

This module also assigns a GapPriority, based on how the TARGET job
description itself framed the requirement (required/preferred/
responsibility/competency) — deliberately NOT based on cross-JD
frequency. The brief is explicit that frequency alone must never be
treated as proof of importance; priority here comes from the target
vacancy's own stated framing, which is a different, defensible signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import EvidenceStatus, RequirementCategory, GapPriority
from evidence_mapper import EvidenceMatrixResult, EvidenceMatrixRow


class GapMessageType:
    """
    A closed set of four message types. Every GapAnalysisEntry has
    exactly one of these, chosen solely by evidence_status — see
    _message_type_for_status(), the single place this mapping happens.
    """
    HAS_SKILL = "has_skill"                        # strong, direct evidence
    TRANSFERABLE_EVIDENCE = "transferable_evidence"  # related evidence, different context
    NEEDS_STRONGER_EVIDENCE = "needs_stronger_evidence"  # weaker/partial evidence
    CONSIDER_DEVELOPING = "consider_developing"      # no evidence found at all


@dataclass
class GapAnalysisEntry:
    requirement: str
    jd_frequency: str
    target_jd_category: str | None
    evidence_status: str
    evidence_source: str
    evidence_snippet: str
    message_type: str
    message: str
    priority: str  # GapPriority value


@dataclass
class GapAnalysisResult:
    entries: list[GapAnalysisEntry] = field(default_factory=list)

    def by_message_type(self, message_type: str) -> list[GapAnalysisEntry]:
        return [e for e in self.entries if e.message_type == message_type]

    def by_priority(self, priority: str) -> list[GapAnalysisEntry]:
        return [e for e in self.entries if e.priority == priority]

    @property
    def strong_matches(self) -> list[GapAnalysisEntry]:
        return self.by_message_type(GapMessageType.HAS_SKILL)

    @property
    def transferable(self) -> list[GapAnalysisEntry]:
        return self.by_message_type(GapMessageType.TRANSFERABLE_EVIDENCE)

    @property
    def needs_stronger_evidence(self) -> list[GapAnalysisEntry]:
        return self.by_message_type(GapMessageType.NEEDS_STRONGER_EVIDENCE)

    @property
    def genuine_gaps(self) -> list[GapAnalysisEntry]:
        return self.by_message_type(GapMessageType.CONSIDER_DEVELOPING)

    @property
    def high_priority_gaps(self) -> list[GapAnalysisEntry]:
        """The gaps most worth the candidate's attention first."""
        return self.by_priority(GapPriority.HIGH)


def analyse_gaps(matrix: EvidenceMatrixResult) -> GapAnalysisResult:
    entries = [_build_entry(row) for row in matrix.rows]
    return GapAnalysisResult(entries=entries)


def _build_entry(row: EvidenceMatrixRow) -> GapAnalysisEntry:
    message_type = _message_type_for_status(row.evidence_status)
    message = _build_message(row, message_type)
    priority = _priority_for(row)

    return GapAnalysisEntry(
        requirement=row.requirement,
        jd_frequency=row.jd_frequency,
        target_jd_category=row.target_jd_category,
        evidence_status=row.evidence_status,
        evidence_source=row.evidence_source,
        evidence_snippet=row.evidence_snippet,
        message_type=message_type,
        message=message,
        priority=priority,
    )


def _message_type_for_status(evidence_status: str) -> str:
    """
    The ONLY place evidence_status is translated into a message type.
    This is a direct, exhaustive mapping — every EvidenceStatus value is
    handled explicitly, so there's no way for e.g. MISSING evidence to
    accidentally produce a "has_skill" message.
    """
    mapping = {
        EvidenceStatus.STRONG_MATCH: GapMessageType.HAS_SKILL,
        EvidenceStatus.TRANSFERABLE: GapMessageType.TRANSFERABLE_EVIDENCE,
        EvidenceStatus.PARTIAL_MATCH: GapMessageType.NEEDS_STRONGER_EVIDENCE,
        EvidenceStatus.MISSING: GapMessageType.CONSIDER_DEVELOPING,
    }
    return mapping[evidence_status]


def _build_message(row: EvidenceMatrixRow, message_type: str) -> str:
    if message_type == GapMessageType.HAS_SKILL:
        return (
            f"You have direct evidence of {row.requirement} in your "
            f"{row.evidence_source} section."
        )

    if message_type == GapMessageType.TRANSFERABLE_EVIDENCE:
        return (
            f"You don't have direct experience with {row.requirement}, but your "
            f"{row.evidence_source} section shows related, transferable evidence. "
            f"Present this honestly as relevant experience — not as direct "
            f"experience you don't have."
        )

    if message_type == GapMessageType.NEEDS_STRONGER_EVIDENCE:
        return (
            f"You have some evidence for {row.requirement} in your "
            f"{row.evidence_source} section, but it may be worth strengthening "
            f"or confirming it clearly supports this requirement."
        )

    # CONSIDER_DEVELOPING
    return (
        f"No evidence was found for {row.requirement} anywhere in your CV. "
        f"Consider whether you have relevant experience worth adding, or "
        f"whether this is a genuine skill gap worth developing. This should "
        f"not be claimed without genuine evidence."
    )


def _priority_for(row: EvidenceMatrixRow) -> str:
    """
    Priority is driven by the TARGET job description's own framing of the
    requirement (required/preferred/responsibility/competency), combined
    with how strong the CV's evidence is. It is NOT driven by cross-JD
    frequency — see the module docstring for why that distinction matters.
    """
    if row.evidence_status == EvidenceStatus.STRONG_MATCH:
        return GapPriority.NONE

    category = row.target_jd_category

    if category == RequirementCategory.REQUIRED:
        if row.evidence_status == EvidenceStatus.MISSING:
            return GapPriority.HIGH
        # PARTIAL_MATCH or TRANSFERABLE against a required item still
        # deserves real attention before applying.
        return GapPriority.MEDIUM

    if category == RequirementCategory.PREFERRED:
        if row.evidence_status == EvidenceStatus.MISSING:
            return GapPriority.MEDIUM
        return GapPriority.LOW

    # RESPONSIBILITY, COMPETENCY, or not present in the target JD at all
    # (only seen in similar JDs) — real, but lower stakes for this
    # specific application.
    return GapPriority.LOW
