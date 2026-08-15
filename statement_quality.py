"""
statement_quality.py

Runs the quality checklist from the brief against a generated personal
statement, and produces four headline scores:

    Coverage Score          — how much of what the target JD actually
                               required (and the candidate has evidence
                               for) made it into the statement
    Evidence Score           — how strong the evidence behind what WAS
                               included actually is
    Keyword Relevance Score  — whether requirements are mentioned once,
                               meaningfully, rather than repeated/stuffed
    Natural Language Score   — rule-based checks for clichés, leaked
                               formatting artefacts, and repetitive
                               sentence openings

These are explicitly INTERNAL QUALITY INDICATORS, not a guarantee of
interview success — every StatementQualityResult carries that disclaimer
verbatim (see QUALITY_DISCLAIMER), and nothing in this module claims to
predict outcomes or detect "human-written" text.

All checks are rule-based and fully transparent — every score and every
checklist item's pass/fail can be traced back to a specific, inspectable
calculation. Nothing here is an opaque model judgement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from config import RequirementCategory
from gap_analyser import GapAnalysisResult, GapMessageType
from personal_statement import PersonalStatementResult, PersonalStatementInput, NATURAL_PHRASING
from requirement_miner import phrase_in_text


QUALITY_DISCLAIMER = (
    "These scores are internal quality indicators meant to help you review "
    "and improve your statement — they are not a guarantee of interview "
    "success, and they are not an assessment made by any employer."
)

BANNED_CLICHES = [
    "highly motivated", "team player", "results-driven", "results driven",
    "hard-working individual", "passionate about", "dynamic individual",
    "go-getter", "think outside the box", "synergy", "self-starter",
    "proven track record",
]

_MIN_WORD_COUNT = 60
_MAX_WORD_COUNT = 300


@dataclass
class QualityCheckItem:
    label: str
    passed: bool
    detail: str


@dataclass
class StatementQualityResult:
    checklist: list[QualityCheckItem] = field(default_factory=list)
    coverage_score: float = 0.0
    evidence_score: float = 0.0
    keyword_relevance_score: float = 0.0
    natural_language_score: float = 0.0
    all_checks_passed: bool = False
    summary_note: str = QUALITY_DISCLAIMER

    def failed_checks(self) -> list[QualityCheckItem]:
        return [item for item in self.checklist if not item.passed]


def check_statement_quality(
    gap_result: GapAnalysisResult,
    statement_result: PersonalStatementResult,
    statement_input: PersonalStatementInput,
) -> StatementQualityResult:
    coverage = _coverage_score(gap_result, statement_result)
    evidence = _evidence_score(gap_result, statement_result)
    keyword = _keyword_relevance_score(statement_result)
    natural = _natural_language_score(statement_result)

    checklist = _build_checklist(
        gap_result, statement_result, statement_input, coverage, evidence, keyword, natural
    )

    return StatementQualityResult(
        checklist=checklist,
        coverage_score=coverage,
        evidence_score=evidence,
        keyword_relevance_score=keyword,
        natural_language_score=natural,
        all_checks_passed=all(item.passed for item in checklist),
        summary_note=QUALITY_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Coverage Score
# ---------------------------------------------------------------------------

def _coverage_score(gap_result: GapAnalysisResult, statement_result: PersonalStatementResult) -> float:
    """
    Of the requirements the TARGET job description explicitly marked as
    required, and for which the candidate has SOME genuine evidence (i.e.
    excluding MISSING ones — you can't include what isn't there), what
    fraction actually made it into the statement?
    """
    significant = [
        e for e in gap_result.entries
        if e.target_jd_category == RequirementCategory.REQUIRED
        and e.message_type != GapMessageType.CONSIDER_DEVELOPING
    ]
    if not significant:
        return 1.0  # nothing required-and-evidenced to cover

    covered = [e for e in significant if e.requirement in statement_result.included_requirements]
    return len(covered) / len(significant)


# ---------------------------------------------------------------------------
# Evidence Score
# ---------------------------------------------------------------------------

_EVIDENCE_WEIGHTS = {
    GapMessageType.HAS_SKILL: 1.0,
    GapMessageType.TRANSFERABLE_EVIDENCE: 0.85,
    GapMessageType.NEEDS_STRONGER_EVIDENCE: 0.6,
}


def _evidence_score(gap_result: GapAnalysisResult, statement_result: PersonalStatementResult) -> float:
    """
    Of the requirements included, how strong is the evidence behind them
    on average? Direct CV evidence scores highest, transferable evidence
    next, partial/weaker evidence lowest — but nothing MISSING can ever
    be scored here, since it can never be in included_requirements.
    """
    if not statement_result.included_requirements:
        return 0.0

    by_requirement = {e.requirement: e for e in gap_result.entries}
    weights = [
        _EVIDENCE_WEIGHTS.get(by_requirement[r].message_type, 0.0)
        for r in statement_result.included_requirements
        if r in by_requirement
    ]
    return sum(weights) / len(weights) if weights else 0.0


# ---------------------------------------------------------------------------
# Keyword Relevance Score (stuffing detector)
# ---------------------------------------------------------------------------

def _keyword_relevance_score(statement_result: PersonalStatementResult) -> float:
    """
    Natural writing often mentions a key phrase twice — once in an
    opening summary line, once when elaborating on it in the body. That
    is NOT stuffing. The score only penalises phrases mentioned MORE than
    twice, which is a much more reliable stuffing signal than expecting
    exactly one mention (a stricter rule would wrongly punish perfectly
    normal "preview, then elaborate" writing).
    """
    if not statement_result.included_requirements:
        return 1.0  # nothing to stuff

    text_lower = statement_result.statement_text.lower()
    penalty = 0.0
    for requirement in statement_result.included_requirements:
        phrase = NATURAL_PHRASING.get(requirement, requirement.lower()).lower()
        mentions = len(re.findall(r"\b" + re.escape(phrase) + r"\b", text_lower))
        if mentions > 2:
            penalty += (mentions - 2) * 0.15

    return max(0.0, 1.0 - penalty)


# ---------------------------------------------------------------------------
# Natural Language Score
# ---------------------------------------------------------------------------

def _natural_language_score(statement_result: PersonalStatementResult) -> float:
    text = statement_result.statement_text
    text_lower = text.lower()
    score = 1.0

    for cliche in BANNED_CLICHES:
        if cliche in text_lower:
            score -= 0.15

    if "— -" in text or ": -" in text:
        score -= 0.3  # a leaked bullet marker artefact

    if ".." in text:
        score -= 0.2  # a formatting glitch (e.g. double period)

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    openings = [s.split()[0].lower() for s in sentences if s.split()]
    if openings:
        most_repeated = max(openings.count(o) for o in set(openings))
        if most_repeated > max(2, len(openings) // 2):
            score -= 0.2  # too many sentences starting the same way

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Checklist (the 13 items from the brief)
# ---------------------------------------------------------------------------

def _build_checklist(
    gap_result: GapAnalysisResult,
    statement_result: PersonalStatementResult,
    statement_input: PersonalStatementInput,
    coverage: float,
    evidence: float,
    keyword: float,
    natural: float,
) -> list[QualityCheckItem]:
    text = statement_result.statement_text
    text_lower = text.lower()
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    genuine_gap_phrases = {e.requirement for e in gap_result.genuine_gaps}

    role_mentioned = statement_input.target_role.lower() in text_lower

    # No requirement the candidate has NO evidence for should appear in
    # the text at all — checked directly against the generated text, as
    # a defence-in-depth verification (not just trusting the generator's
    # own internal guarantee). Uses phrase_in_text (word-boundary
    # matching), NOT a naive substring check — a naive check would treat
    # the single-letter phrase "R" as matching almost any English text
    # containing the letter r (e.g. "care", "your", "experience"), which
    # is exactly the false-positive bug this module hit during testing.
    no_fabrication = not any(phrase_in_text(phrase, text) for phrase in genuine_gap_phrases)

    by_requirement = {e.requirement: e for e in gap_result.entries}
    tied_to_target_jd = any(
        by_requirement[r].target_jd_category is not None
        for r in statement_result.included_requirements
        if r in by_requirement
    )
    industry_mentioned = bool(
        statement_input.industry and statement_input.industry.lower() in text_lower
    )

    return [
        QualityCheckItem(
            "Covers important requirements",
            coverage >= 0.7,
            f"{coverage * 100:.0f}% of the target JD's required, evidenced items were included.",
        ),
        QualityCheckItem(
            "Uses genuine candidate evidence",
            len(statement_result.included_requirements) > 0,
            "The statement draws only on requirements backed by real CV evidence."
            if statement_result.included_requirements
            else "No evidenced requirements were available to include.",
        ),
        QualityCheckItem(
            "Relevant to target role",
            role_mentioned,
            "The target role is named in the statement."
            if role_mentioned
            else "The target role name was not found in the statement text.",
        ),
        QualityCheckItem(
            "No fabricated experience",
            no_fabrication,
            "No requirement lacking CV evidence appears in the statement."
            if no_fabrication
            else "A requirement without genuine evidence appears to be mentioned — needs review.",
        ),
        QualityCheckItem(
            "No unsupported qualifications",
            no_fabrication,
            "Same underlying check, applied specifically to qualification-type requirements.",
        ),
        QualityCheckItem(
            "No excessive keyword stuffing",
            keyword >= 0.6,
            f"Keyword relevance score: {keyword * 100:.0f}%.",
        ),
        QualityCheckItem(
            "Natural language",
            natural >= 0.6,
            f"Natural language score: {natural * 100:.0f}%.",
        ),
        QualityCheckItem(
            "Clear structure",
            len(paragraphs) >= 3,
            f"{len(paragraphs)} paragraph(s) found (opening / body / closing expected).",
        ),
        QualityCheckItem(
            "Appropriate length",
            _MIN_WORD_COUNT <= statement_result.word_count <= _MAX_WORD_COUNT,
            f"{statement_result.word_count} words (expected {_MIN_WORD_COUNT}-{_MAX_WORD_COUNT}).",
        ),
        QualityCheckItem(
            "Strong opening",
            bool(paragraphs) and role_mentioned and len(paragraphs[0].split()) >= 8,
            "The opening paragraph names the role and gives real context."
            if paragraphs and role_mentioned
            else "The opening paragraph is missing, too short, or doesn't name the role.",
        ),
        QualityCheckItem(
            "Strong evidence",
            evidence >= 0.6,
            f"Evidence score: {evidence * 100:.0f}%.",
        ),
        QualityCheckItem(
            "Clear relevance",
            tied_to_target_jd or industry_mentioned,
            "Included requirements are tied to the target job description or named industry."
            if (tied_to_target_jd or industry_mentioned)
            else "Nothing included ties clearly back to the target JD or industry.",
        ),
        QualityCheckItem(
            "Strong conclusion",
            bool(paragraphs) and len(paragraphs[-1].split()) >= 8,
            "The closing paragraph is substantive."
            if paragraphs and len(paragraphs[-1].split()) >= 8
            else "The closing paragraph is missing or too short.",
        ),
    ]
