"""
evidence_mapper.py

This is the core of the evidence-based approach: for every requirement
identified by frequency_analyser.py, determine whether the candidate's CV
provides genuine evidence for it — and if so, how strong that evidence is.

Produces exactly the table shape described in the brief:
    Requirement | JD Frequency | Target JD | CV Evidence | Evidence Source | Gap

Evidence strength (see config.EvidenceStatus) is deliberately NOT a single
yes/no:
  - STRONG_MATCH   — the phrase appears in the CV's Skills or Experience
                      section (i.e. a real, claimed skill or job duty).
  - PARTIAL_MATCH  — the phrase appears elsewhere in the CV (e.g.
                      Certifications, Education, Summary) — real, but
                      weaker evidence than a skill/experience entry.
  - TRANSFERABLE   — the exact phrase isn't in the CV, but a related term
                      is present in a DIFFERENT context (typically a
                      personal Project rather than paid Experience) — e.g.
                      "Healthcare/NHS data experience" has no direct match,
                      but the CV's Projects section mentions an NHS A&E
                      project. This is flagged as transferable, never
                      claimed as direct experience.
  - MISSING        — no evidence found anywhere. The matrix says so
                      plainly; nothing is invented to fill the gap.

This module never edits or scores the CV — it only reports what it found
and where. Turning this into recommendations/gap severity is
gap_analyser.py's job (next module).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from config import EvidenceStatus
from cv_parser import CVParseResult
from frequency_analyser import FrequencyAnalysisResult, FrequencyEntry
from requirement_miner import KNOWN_PHRASES, phrase_in_text


# ---------------------------------------------------------------------------
# Where to look for evidence, and in what order of strength.
#
# Skills/Experience are treated as the strongest evidence — they're where
# a candidate states a claimed skill or an actual paid job duty.
# Certifications/Education/Summary are treated as weaker but still real.
# Projects are checked separately (see TRANSFERABLE handling below),
# because personal projects are genuine evidence of ability but are not
# the same as paid employment experience — the brief is explicit that we
# must not blur that distinction.
# ---------------------------------------------------------------------------

STRONG_EVIDENCE_SECTIONS = ["experience", "skills"]
PARTIAL_EVIDENCE_SECTIONS = ["certifications", "education", "summary"]
PROJECT_SECTION = "projects"


# ---------------------------------------------------------------------------
# Transferable-evidence hints.
#
# Some requirements (notably sector/employer-context ones like "NHS data
# experience") will almost never appear as a literal phrase match in a
# candidate's CV unless they've genuinely worked there. But a candidate
# might still have real, relevant evidence in a DIFFERENT form — e.g. a
# personal project analysing public NHS data. These hints let us surface
# that connection explicitly as "transferable", rather than either (a)
# missing it entirely, or (b) wrongly claiming direct experience.
#
# Each entry: canonical_phrase -> list of loosely related terms to search
# for, specifically within the Projects (and, cautiously, Experience)
# sections, when the strict phrase match already failed.
# ---------------------------------------------------------------------------

TRANSFERABLE_HINTS: dict[str, list[str]] = {
    "Healthcare/NHS data experience": ["nhs", "a&e", "hospital", "healthcare"],
}


@dataclass
class EvidenceMatrixRow:
    requirement: str                 # canonical phrase, e.g. "SQL"
    jd_frequency: str                # e.g. "3/3"
    target_jd_category: str | None   # RequirementCategory value, or None
    evidence_status: str             # config.EvidenceStatus value
    evidence_source: str             # CV section name, or "" if missing
    evidence_snippet: str            # the CV line/text that supports it, or ""
    gap: str                         # human-readable explanation

    @property
    def cv_evidence_label(self) -> str:
        """Short YES/PARTIAL/TRANSFERABLE/NO label, matching the brief's example table."""
        return {
            EvidenceStatus.STRONG_MATCH: "YES",
            EvidenceStatus.PARTIAL_MATCH: "PARTIAL",
            EvidenceStatus.TRANSFERABLE: "TRANSFERABLE",
            EvidenceStatus.MISSING: "NO",
        }[self.evidence_status]


@dataclass
class EvidenceMatrixResult:
    rows: list[EvidenceMatrixRow] = field(default_factory=list)

    def row_for(self, requirement: str) -> EvidenceMatrixRow | None:
        for row in self.rows:
            if row.requirement == requirement:
                return row
        return None

    def rows_by_status(self, status: str) -> list[EvidenceMatrixRow]:
        return [r for r in self.rows if r.evidence_status == status]


def build_evidence_matrix(
    cv_result: CVParseResult, frequency_result: FrequencyAnalysisResult
) -> EvidenceMatrixResult:
    """
    Build the Evidence Matrix by checking, for each requirement identified
    across the target + similar job descriptions, whether the CV provides
    genuine evidence — and how strong that evidence is.
    """
    if not cv_result.is_valid:
        # An invalid CV can't provide evidence for anything — every
        # requirement is MISSING. We still return a full matrix (rather
        # than an empty one) so downstream code has a consistent shape to
        # work with regardless of whether the CV parsed successfully.
        return EvidenceMatrixResult(
            rows=[
                _missing_row(entry, "The CV could not be read — no evidence available.")
                for entry in frequency_result.entries
            ]
        )

    rows = [_build_row(cv_result, entry) for entry in frequency_result.entries]
    return EvidenceMatrixResult(rows=rows)


def _build_row(cv_result: CVParseResult, entry: FrequencyEntry) -> EvidenceMatrixRow:
    canonical = entry.canonical_phrase
    forms = [canonical, *KNOWN_PHRASES.get(canonical, [])]

    # 1. Strongest evidence: Skills or Experience sections.
    for section in STRONG_EVIDENCE_SECTIONS:
        text = cv_result.section(section)
        if not text:
            continue
        matched_form = _first_matching_form(forms, text)
        if matched_form:
            return EvidenceMatrixRow(
                requirement=canonical,
                jd_frequency=entry.frequency_fraction,
                target_jd_category=entry.target_jd_category,
                evidence_status=EvidenceStatus.STRONG_MATCH,
                evidence_source=section,
                evidence_snippet=_extract_snippet(text, matched_form),
                gap=f"Direct evidence found in the CV's {section} section.",
            )

    # 2. Weaker but genuine evidence: Certifications, Education, Summary.
    for section in PARTIAL_EVIDENCE_SECTIONS:
        text = cv_result.section(section)
        if not text:
            continue
        matched_form = _first_matching_form(forms, text)
        if matched_form:
            return EvidenceMatrixRow(
                requirement=canonical,
                jd_frequency=entry.frequency_fraction,
                target_jd_category=entry.target_jd_category,
                evidence_status=EvidenceStatus.PARTIAL_MATCH,
                evidence_source=section,
                evidence_snippet=_extract_snippet(text, matched_form),
                gap=(
                    f"Evidence found in the CV's {section} section, but not as a "
                    f"stated skill or work experience — worth confirming this is "
                    f"strong enough evidence for this requirement."
                ),
            )

    # 3. Transferable evidence: related terms in Projects (not a direct
    #    phrase match, and NOT claimed as paid experience).
    hints = TRANSFERABLE_HINTS.get(canonical)
    if hints:
        project_text = cv_result.section(PROJECT_SECTION)
        if project_text:
            matched_hint = _first_matching_form(hints, project_text)
            if matched_hint:
                return EvidenceMatrixRow(
                    requirement=canonical,
                    jd_frequency=entry.frequency_fraction,
                    target_jd_category=entry.target_jd_category,
                    evidence_status=EvidenceStatus.TRANSFERABLE,
                    evidence_source=PROJECT_SECTION,
                    evidence_snippet=_extract_snippet(project_text, matched_hint),
                    gap=(
                        "No direct employment/skills evidence found, but a related "
                        "personal project provides transferable evidence. Do not "
                        "present this as direct experience — describe it honestly "
                        "as a relevant project."
                    ),
                )

    # 4. Nothing found anywhere.
    return _missing_row(entry, "No evidence found anywhere in the CV.")


def _missing_row(entry: FrequencyEntry, gap_message: str) -> EvidenceMatrixRow:
    return EvidenceMatrixRow(
        requirement=entry.canonical_phrase,
        jd_frequency=entry.frequency_fraction,
        target_jd_category=entry.target_jd_category,
        evidence_status=EvidenceStatus.MISSING,
        evidence_source="",
        evidence_snippet="",
        gap=gap_message,
    )


def _first_matching_form(forms: list[str], text: str) -> str | None:
    for form in forms:
        if phrase_in_text(form, text):
            return form
    return None


def _extract_snippet(text: str, matched_form: str) -> str:
    """
    Returns a short, human-readable pointer to exactly where the evidence
    came from — not the whole section.

    Handles two real formatting quirks CVs commonly have:
      1. A bullet WRAPPED across multiple physical lines (e.g. a plain
         .txt CV where a long bullet point continues on an indented
         second line). Without merging these back into one logical line
         first, the snippet would be truncated mid-sentence at whatever
         the line-wrap happened to cut off.
      2. A comma-separated LIST line (e.g. a Skills section written as
         "SQL, Excel, Power BI, Python") — where every skill on the line
         would otherwise return the exact same whole-line snippet.
    """
    for line in _merge_wrapped_lines(text):
        if phrase_in_text(matched_form, line):
            return _trim_list_line(line, matched_form)
    return text.strip()[:120]  # fallback, shouldn't normally be hit


_BULLET_START = re.compile(r"^[-•*▪●○]|^\d+[.)]")


def _merge_wrapped_lines(text: str) -> list[str]:
    """
    Joins soft-wrapped continuation lines back into a single logical
    line. A physical line is treated as a CONTINUATION of the previous
    one (rather than a new item) when it doesn't start a new bullet AND
    the previous line doesn't already end with sentence-ending
    punctuation — which is exactly the pattern a wrapped bullet produces:
    the first line ends mid-sentence, and the wrapped remainder starts
    with plain indented text, not a new bullet marker.
    """
    lines = [raw.strip() for raw in text.split("\n")]
    merged: list[str] = []

    for line in lines:
        if not line:
            continue
        starts_new_item = (
            not merged
            or _BULLET_START.match(line) is not None
            or merged[-1].endswith((".", "!", "?", ":"))
        )
        if starts_new_item:
            merged.append(line)
        else:
            merged[-1] = f"{merged[-1]} {line}"

    return merged


def _trim_list_line(line: str, matched_form: str) -> str:
    # Split on commas EXCEPT commas inside parentheses — otherwise an
    # entry like "Python (pandas, basic)" gets wrongly split into
    # "Python (pandas" and "basic)", truncating it mid-parenthesis.
    parts = [p.strip() for p in re.split(r",(?![^(]*\))", line)]
    # 4+ comma-separated parts is a reasonable heuristic for "this is a
    # list of items", not a prose sentence that happens to contain a
    # comma (e.g. "Cleaned data, then built a dashboard." has 2 parts and
    # stays intact as a full sentence).
    if len(parts) >= 4:
        for part in parts:
            if phrase_in_text(matched_form, part):
                return part
    return line
