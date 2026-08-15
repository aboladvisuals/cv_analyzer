"""
optimiser.py

Implements the CV optimisation workflow from the brief:

    Original CV -> Job analysis -> Gap analysis -> Recommended changes
    -> User approval -> Optimised CV

This module produces the "Recommended changes" step — it does NOT
automatically rewrite anything, and there is no code path here that
applies a change without the caller explicitly deciding to. Actually
writing an approved, edited CV back out to a file is Export (a later
phase, not yet built) — this module's job stops at producing reviewable
suggestions.

Two deliberately different kinds of output, because they carry different
levels of certainty:

  CVEditSuggestion — a concrete BEFORE/AFTER wording change. Only
      generated where we have genuine, factual material already in the
      CV to work from (currently: TRANSFERABLE evidence, e.g. making an
      existing project's relevance to a requirement explicit). No new
      fact is ever introduced — the proposed wording only makes an
      existing true connection more explicit.

  CVRecommendation — advice, with NO proposed wording. Generated when a
      change might genuinely help, but we don't have enough factual
      material to safely draft one ourselves (e.g. "a bare skills-list
      entry could be stronger with a specific example — add one if you
      have one"). Never invents the example itself.

A requirement with NO evidence anywhere in the CV (config.EvidenceStatus
.MISSING / GapMessageType.CONSIDER_DEVELOPING) NEVER produces a
suggestion or recommendation to add wording for it — it is only listed
under `unaddressed_gaps`. This is enforced the same way personal_statement
.py enforces it: message_type is checked before anything is generated,
not after.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import RequirementCategory
from gap_analyser import GapAnalysisResult, GapAnalysisEntry, GapMessageType
from personal_statement import NATURAL_PHRASING


OPTIMISATION_DISCLAIMER = (
    "These are suggested wording changes and recommendations based only on "
    "evidence already in your CV. Nothing here should be added unless it is "
    "genuinely true — review every suggestion, and reject anything that "
    "doesn't accurately reflect your experience. Nothing is changed "
    "automatically; you decide what, if anything, to use."
)


@dataclass
class CVEditSuggestion:
    requirement: str
    section: str
    original_wording: str
    proposed_wording: str
    reason: str
    approved: bool | None = None  # None = not yet reviewed by the user


@dataclass
class CVRecommendation:
    requirement: str
    section: str | None
    advice: str
    reason: str


@dataclass
class OptimisationResult:
    suggestions: list[CVEditSuggestion] = field(default_factory=list)
    recommendations: list[CVRecommendation] = field(default_factory=list)
    unaddressed_gaps: list[str] = field(default_factory=list)
    disclaimer: str = OPTIMISATION_DISCLAIMER

    def approved_suggestions(self) -> list[CVEditSuggestion]:
        return [s for s in self.suggestions if s.approved is True]


def generate_optimisation_suggestions(gap_result: GapAnalysisResult) -> OptimisationResult:
    suggestions: list[CVEditSuggestion] = []
    recommendations: list[CVRecommendation] = []
    unaddressed: list[str] = []

    for entry in gap_result.entries:
        if entry.message_type == GapMessageType.CONSIDER_DEVELOPING:
            # No evidence anywhere in the CV. Never suggest wording for
            # this — not even advice implying it could be added.
            unaddressed.append(entry.requirement)
            continue

        if entry.message_type == GapMessageType.TRANSFERABLE_EVIDENCE:
            suggestions.append(_build_transferable_suggestion(entry))
        elif entry.message_type == GapMessageType.HAS_SKILL:
            recommendation = _build_has_skill_recommendation(entry)
            if recommendation:
                recommendations.append(recommendation)
        elif entry.message_type == GapMessageType.NEEDS_STRONGER_EVIDENCE:
            recommendations.append(_build_needs_stronger_recommendation(entry))

    return OptimisationResult(
        suggestions=suggestions,
        recommendations=recommendations,
        unaddressed_gaps=unaddressed,
    )


def _build_transferable_suggestion(entry: GapAnalysisEntry) -> CVEditSuggestion:
    phrase = NATURAL_PHRASING.get(entry.requirement, entry.requirement.lower())
    original = entry.evidence_snippet
    proposed = (
        f"{original.rstrip('.')} — directly relevant to {phrase}, demonstrating "
        f"transferable experience I can apply in this role."
    )

    if entry.target_jd_category == RequirementCategory.REQUIRED:
        framing = "an explicit requirement of this role"
    elif entry.target_jd_category is not None:
        framing = "something this role values"
    else:
        framing = "something that comes up repeatedly across similar adverts"

    reason = (
        f"{phrase.capitalize()} is {framing}, and your {entry.evidence_source} "
        f"section already contains genuine, relevant evidence. Making the "
        f"connection explicit strengthens this without adding anything untrue "
        f"— it still describes a project, not paid employment."
    )

    return CVEditSuggestion(
        requirement=entry.requirement,
        section=entry.evidence_source,
        original_wording=original,
        proposed_wording=proposed,
        reason=reason,
    )


def _build_has_skill_recommendation(entry: GapAnalysisEntry) -> CVRecommendation | None:
    # HAS_SKILL evidence is checked against "experience" before "skills"
    # (see evidence_mapper.STRONG_EVIDENCE_SECTIONS) — so if the source
    # here is "skills", that means it was NOT also found in a richer,
    # more descriptive section. A bare skills-list entry is real evidence,
    # but weaker than a demonstrated example.
    if entry.evidence_source != "skills":
        return None  # already well-represented elsewhere — nothing to suggest

    phrase = NATURAL_PHRASING.get(entry.requirement, entry.requirement.lower())
    return CVRecommendation(
        requirement=entry.requirement,
        section=entry.evidence_source,
        advice=(
            f"'{phrase}' currently only appears as a bare skills-list entry. "
            f"If you have a genuine example of using it, adding a specific "
            f"bullet under Experience or Projects would make this evidence "
            f"stronger — but only add this if it's genuinely true."
        ),
        reason="A demonstrated example is generally stronger evidence than a skills list alone.",
    )


def _build_needs_stronger_recommendation(entry: GapAnalysisEntry) -> CVRecommendation:
    phrase = NATURAL_PHRASING.get(entry.requirement, entry.requirement.lower())
    return CVRecommendation(
        requirement=entry.requirement,
        section=entry.evidence_source,
        advice=(
            f"Evidence for '{phrase}' currently comes from your "
            f"{entry.evidence_source} section rather than Skills or "
            f"Experience. If genuinely applicable, consider whether a "
            f"Skills or Experience bullet could reflect this more directly."
        ),
        reason=(
            f"Evidence from {entry.evidence_source} is real, but generally "
            f"reads as weaker than a demonstrated skill or work experience."
        ),
    )
