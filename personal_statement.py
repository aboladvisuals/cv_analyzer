"""
personal_statement.py

Assembles a personal statement at one of three tiers (config.StatementTier):

    MASTER   — reusable across employers for the SAME ROLE. Built from
               requirements that recur across the similar job descriptions
               (the "common denominator"), never from one employer's
               specific wording.
    INDUSTRY — the Master statement's evidence, re-weighted toward
               requirements connected to a given industry/sector.
    VACANCY  — tailored to the ONE target job description, prioritising
               whatever it explicitly asked for.

HARD RULE, enforced structurally: only GapAnalysisEntry objects whose
message_type is HAS_SKILL, TRANSFERABLE_EVIDENCE, or
NEEDS_STRONGER_EVIDENCE are ever eligible for inclusion. CONSIDER_DEVELOPING
entries (config.EvidenceStatus.MISSING) can NEVER appear in generated
text — see _eligible_entries(). There is no path in this module that
writes a sentence from an entry with no genuine evidence behind it.

This is a rule-based scaffold, not a language model. It produces
correctly-structured, evidence-grounded prose, but the phrasing is
templated and will read as more mechanical than something a skilled human
(or an LLM) would write. That's a known, deliberate limitation for this
phase — see the original brief's own guidance that natural phrasing is a
good fit for an optional AI layer, while the core application must work
without one. Nothing here claims to guarantee "human-sounding" text or
passing any AI-detection tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from config import StatementTier
from gap_analyser import GapAnalysisResult, GapAnalysisEntry, GapMessageType
from evidence_mapper import TRANSFERABLE_HINTS


# ---------------------------------------------------------------------------
# Natural-language phrasing for canonical requirement phrases.
#
# Canonical phrases (e.g. "Healthcare/NHS data experience") are good for
# matching but read awkwardly dropped straight into a sentence. This maps
# each one to a short, natural phrase for embedding in generated prose.
# Falls back to the canonical phrase itself (lowercased) if not listed.
# ---------------------------------------------------------------------------

NATURAL_PHRASING: dict[str, str] = {
    "SQL": "SQL",
    "Excel": "Excel",
    "Power BI": "Power BI",
    "Python": "Python",
    "R": "R",
    "Data visualisation": "data visualisation",
    "Dashboards": "building dashboards",
    "Stakeholder communication": "communicating data insights to stakeholders",
    "Data quality": "data quality assurance",
    "Healthcare/NHS data experience": "healthcare data analysis",
    "Degree-level education": "degree-level education",
    "Teamwork": "teamwork and collaboration",
    "Continuous improvement": "continuous improvement",
    "Patient/public focus": "a patient and public-focused approach",
    "Analytical thinking": "analytical thinking",
    "Attention to detail": "attention to detail",
    "Performance reporting": "performance reporting",

    # Matches the "Expanded vocabulary" additions in requirement_miner.py
    "Tableau": "Tableau",
    "Looker": "Looker",
    "Qlik": "Qlik",
    "SAS": "SAS",
    "Google Analytics": "Google Analytics",
    "A/B testing": "A/B testing",
    "Machine learning": "machine learning",
    "Statistical analysis": "statistical analysis",
    "Data warehousing": "data warehousing",
    "ETL": "ETL processes",
    "Git": "Git and version control",
    "AWS": "AWS",
    "Microsoft Azure": "Microsoft Azure",
    "Google Cloud Platform": "Google Cloud Platform",
    "Docker": "Docker",
    "Kubernetes": "Kubernetes",
    "SQL Server": "SQL Server",
    "Java programming": "Java",
    "JavaScript": "JavaScript",
    "C programming": "C programming",
    "C++": "C++",
    "Go programming": "Go",
    "Salesforce": "Salesforce",
    "SAP": "SAP",
    "VBA": "VBA",
    "Leadership": "leadership",
    "Project management": "project management",
    "Time management": "time management",
    "Problem solving": "problem solving",
    "Mentoring": "mentoring",
    "Presentation skills": "presentation skills",
    "Negotiation": "negotiation",
    "Adaptability": "adaptability",
    "Customer service": "customer service",
    "Budget management": "budget management",
    "Agile": "Agile methodologies",
    "PRINCE2": "PRINCE2",
    "PMP": "PMP",
    "GDPR": "GDPR and data protection",
    "Data governance": "data governance",

    # Matches the early years / childcare / local government additions
    "EYFS": "the EYFS framework",
    "Safeguarding": "safeguarding",
    "Special educational needs (SEND)": "supporting children with special educational needs",
    "Ofsted": "Ofsted requirements",
    "Child development": "child development",
    "Paediatric first aid": "paediatric first aid",
    "DBS check": "a DBS check",
    "Behaviour management": "behaviour management",
    "Parental engagement": "parental engagement",
    "Child protection": "child protection",
    "Multi-agency working": "multi-agency working",
    "Level 3 childcare qualification": "a Level 3 childcare qualification",
    "Key worker (childcare)": "acting as a key worker",
    "Inclusive practice": "inclusive practice",
    "Local authority": "working with the local authority",
    "Case management": "case management",
    "Social work": "social work",
}


@dataclass
class PersonalStatementInput:
    target_role: str
    tier: str                      # config.StatementTier value
    organisation: str | None = None  # only used for VACANCY tier openings
    industry: str | None = None      # required for INDUSTRY tier


@dataclass
class PersonalStatementResult:
    tier: str
    statement_text: str
    included_requirements: list[str] = field(default_factory=list)
    excluded_requirements: list[str] = field(default_factory=list)
    limitation_note: str = ""
    word_count: int = 0


MASTER_LIMITATION_NOTE = (
    "Your Master Statement is designed for reuse across the same role, but "
    "individual vacancies may contain specific requirements that are worth "
    "addressing separately."
)


def generate_personal_statement(
    gap_result: GapAnalysisResult, statement_input: PersonalStatementInput
) -> PersonalStatementResult:
    tier = statement_input.tier

    if tier == StatementTier.MASTER:
        return _generate_master(gap_result, statement_input)
    if tier == StatementTier.INDUSTRY:
        if not statement_input.industry:
            raise ValueError("An industry must be provided for an INDUSTRY-tier statement.")
        return _generate_industry(gap_result, statement_input)
    if tier == StatementTier.VACANCY:
        return _generate_vacancy(gap_result, statement_input)

    raise ValueError(f"Unknown statement tier: {tier!r}")


# ---------------------------------------------------------------------------
# Eligibility — the one gate every tier must pass through
# ---------------------------------------------------------------------------

_ELIGIBLE_MESSAGE_TYPES = {
    GapMessageType.HAS_SKILL,
    GapMessageType.TRANSFERABLE_EVIDENCE,
    GapMessageType.NEEDS_STRONGER_EVIDENCE,
}


def _eligible_entries(gap_result: GapAnalysisResult) -> list[GapAnalysisEntry]:
    """
    The only entries any tier is allowed to draw from. CONSIDER_DEVELOPING
    (i.e. EvidenceStatus.MISSING — no evidence in the CV at all) is
    excluded here, unconditionally, before any tier-specific selection
    logic runs. No tier can override this.
    """
    return [e for e in gap_result.entries if e.message_type in _ELIGIBLE_MESSAGE_TYPES]


# ---------------------------------------------------------------------------
# MASTER tier
# ---------------------------------------------------------------------------

_MASTER_FREQUENCY_THRESHOLD = 0.5  # appears in at least half the similar JDs


def _generate_master(
    gap_result: GapAnalysisResult, statement_input: PersonalStatementInput
) -> PersonalStatementResult:
    eligible = _eligible_entries(gap_result)
    selected = [e for e in eligible if _frequency_ratio(e) >= _MASTER_FREQUENCY_THRESHOLD]

    if not selected:
        # Fall back to whatever eligible evidence exists rather than
        # producing an empty statement — being reusable across employers
        # doesn't require a minimum threshold to be met to be useful.
        selected = eligible

    selected = _sort_for_master(selected)
    excluded = [e.requirement for e in gap_result.entries if e not in selected]

    text = _assemble_statement(
        opening=_master_opening(statement_input.target_role, selected),
        body_entries=selected,
        closing=(
            f"I'm looking to bring this experience to a {statement_input.target_role} "
            f"role, and I'm keen to keep developing these skills further."
        ),
    )

    return PersonalStatementResult(
        tier=StatementTier.MASTER,
        statement_text=text,
        included_requirements=[e.requirement for e in selected],
        excluded_requirements=excluded,
        limitation_note=MASTER_LIMITATION_NOTE,
        word_count=len(text.split()),
    )


def _sort_for_master(entries: list[GapAnalysisEntry]) -> list[GapAnalysisEntry]:
    # Strongest evidence first, then higher cross-JD frequency — this is
    # about picking the most reusable, best-supported points, not about
    # treating frequency as importance (that distinction stays intact:
    # frequency only breaks ties among equally strong evidence).
    strength_order = {
        GapMessageType.HAS_SKILL: 0,
        GapMessageType.TRANSFERABLE_EVIDENCE: 1,
        GapMessageType.NEEDS_STRONGER_EVIDENCE: 2,
    }
    return sorted(
        entries,
        key=lambda e: (strength_order[e.message_type], -_frequency_ratio(e)),
    )


def _master_opening(target_role: str, selected: list[GapAnalysisEntry]) -> str:
    top_phrases = _top_phrases(selected, count=3)
    if top_phrases:
        return (
            f"I am a {target_role} with practical, evidence-based experience "
            f"across {_join_phrases(top_phrases)}."
        )
    return f"I am a {target_role} with hands-on, evidence-based analytical experience."


# ---------------------------------------------------------------------------
# INDUSTRY tier — Master's selection, re-weighted toward one industry
# ---------------------------------------------------------------------------

def _generate_industry(
    gap_result: GapAnalysisResult, statement_input: PersonalStatementInput
) -> PersonalStatementResult:
    industry = statement_input.industry or ""
    eligible = _eligible_entries(gap_result)

    industry_matches = [e for e in eligible if _relates_to_industry(e.requirement, industry)]
    frequent_matches = [e for e in eligible if _frequency_ratio(e) >= _MASTER_FREQUENCY_THRESHOLD]

    # Industry-relevant evidence is included even below the master
    # frequency threshold — that's the whole point of this tier — then
    # topped up with the usual frequent/reusable evidence, without
    # duplicating entries.
    selected: list[GapAnalysisEntry] = list(industry_matches)
    for entry in frequent_matches:
        if entry not in selected:
            selected.append(entry)

    if not selected:
        selected = eligible

    selected = _sort_for_master(selected)  # same evidence-strength ordering
    excluded = [e.requirement for e in gap_result.entries if e not in selected]

    opening = _industry_opening(statement_input.target_role, industry, selected)
    closing = (
        f"I'm particularly keen to bring this experience to a "
        f"{statement_input.target_role} role within {industry}, where these "
        f"skills feel especially relevant."
    )

    text = _assemble_statement(opening=opening, body_entries=selected, closing=closing)

    return PersonalStatementResult(
        tier=StatementTier.INDUSTRY,
        statement_text=text,
        included_requirements=[e.requirement for e in selected],
        excluded_requirements=excluded,
        limitation_note=MASTER_LIMITATION_NOTE,  # same reusability caveat applies
        word_count=len(text.split()),
    )


def _relates_to_industry(canonical_phrase: str, industry: str) -> bool:
    industry_lower = industry.lower()
    if industry_lower in canonical_phrase.lower():
        return True
    hints = TRANSFERABLE_HINTS.get(canonical_phrase, [])
    return any(industry_lower in hint or hint in industry_lower for hint in hints)


def _industry_opening(target_role: str, industry: str, selected: list[GapAnalysisEntry]) -> str:
    top_phrases = _top_phrases(selected, count=3)
    base = f"I am a {target_role} with practical, evidence-based experience"
    if top_phrases:
        base += f" across {_join_phrases(top_phrases)}"
    return base + f", and a particular interest in applying these skills within {industry.lower()}."


# ---------------------------------------------------------------------------
# VACANCY tier — tailored to the one target job description
# ---------------------------------------------------------------------------

def _generate_vacancy(
    gap_result: GapAnalysisResult, statement_input: PersonalStatementInput
) -> PersonalStatementResult:
    eligible = _eligible_entries(gap_result)
    # Only what the TARGET JD itself actually asked for — not everything
    # that showed up across the similar JDs. This is what makes this
    # tier "tailored to one vacancy" rather than a repeat of Master.
    selected = [e for e in eligible if e.target_jd_category is not None]

    if not selected:
        selected = eligible

    selected = _sort_for_vacancy(selected)
    excluded = [e.requirement for e in gap_result.entries if e not in selected]

    opening = _vacancy_opening(statement_input, selected)
    closing = (
        f"I believe this combination of experience makes me well suited to "
        f"this {statement_input.target_role} role, and I would welcome the "
        f"opportunity to discuss it further."
    )

    text = _assemble_statement(opening=opening, body_entries=selected, closing=closing)

    return PersonalStatementResult(
        tier=StatementTier.VACANCY,
        statement_text=text,
        included_requirements=[e.requirement for e in selected],
        excluded_requirements=excluded,
        limitation_note="",  # no reusability caveat needed — this tier IS vacancy-specific
        word_count=len(text.split()),
    )


def _sort_for_vacancy(entries: list[GapAnalysisEntry]) -> list[GapAnalysisEntry]:
    # Required-in-target-JD first, then preferred, then
    # responsibility/competency — the target JD's own framing decides
    # order, consistent with gap_analyser.py's priority logic.
    from config import RequirementCategory

    category_order = {
        RequirementCategory.REQUIRED: 0,
        RequirementCategory.PREFERRED: 1,
        RequirementCategory.RESPONSIBILITY: 2,
        RequirementCategory.COMPETENCY: 2,
    }
    strength_order = {
        GapMessageType.HAS_SKILL: 0,
        GapMessageType.TRANSFERABLE_EVIDENCE: 1,
        GapMessageType.NEEDS_STRONGER_EVIDENCE: 2,
    }
    return sorted(
        entries,
        key=lambda e: (
            category_order.get(e.target_jd_category, 3),
            strength_order[e.message_type],
        ),
    )


def _vacancy_opening(statement_input: PersonalStatementInput, selected: list[GapAnalysisEntry]) -> str:
    top_phrases = _top_phrases(selected, count=3)
    role = statement_input.target_role
    phrase_clause = f", including {_join_phrases(top_phrases)}" if top_phrases else ""

    if statement_input.organisation:
        return (
            f"I am applying for the {role} role at {statement_input.organisation}, "
            f"bringing practical, evidence-based experience directly relevant to "
            f"this vacancy{phrase_clause}."
        )
    return (
        f"I am a {role} with practical, evidence-based experience directly "
        f"relevant to this role{phrase_clause}."
    )


# ---------------------------------------------------------------------------
# Shared assembly helpers
# ---------------------------------------------------------------------------

_MAX_BODY_ENTRIES = 6  # keeps the statement readable rather than an exhaustive list

_HAS_SKILL_TEMPLATES = [
    "I have practical experience with {phrase}: {snippet}",
    "My work has involved {phrase} directly — {snippet}",
    "{phrase_cap} is something I apply regularly. For example, {snippet_lower}",
]

_TRANSFERABLE_TEMPLATES = [
    "While not yet part of my paid experience, {phrase} is reflected in my "
    "own project work: {snippet}",
    "I've also built relevant experience with {phrase} through independent "
    "project work — {snippet}",
]

_NEEDS_STRONGER_TEMPLATES = [
    "I also have some experience relevant to {phrase}: {snippet}",
]


def _assemble_statement(opening: str, body_entries: list[GapAnalysisEntry], closing: str) -> str:
    # Two different requirement labels (e.g. "Dashboards" and "Power BI")
    # can both be matched from the SAME underlying CV bullet — without
    # deduplicating, the statement would describe that one bullet twice,
    # almost verbatim, as if it were two separate pieces of evidence.
    # Dedupe by evidence_snippet BEFORE capping the body length, so a
    # skipped duplicate doesn't crowd out a genuinely distinct point
    # further down the list.
    seen_snippets: set[str] = set()
    deduped_entries: list[GapAnalysisEntry] = []
    for entry in body_entries:
        snippet_key = entry.evidence_snippet.strip().lower()
        if snippet_key and snippet_key in seen_snippets:
            continue
        seen_snippets.add(snippet_key)
        deduped_entries.append(entry)

    capped_entries = deduped_entries[:_MAX_BODY_ENTRIES]
    body_sentences = [
        _sentence_for(entry, index) for index, entry in enumerate(capped_entries)
    ]
    body_paragraph = " ".join(body_sentences)

    paragraphs = [opening]
    if body_paragraph:
        paragraphs.append(body_paragraph)
    paragraphs.append(closing)

    return "\n\n".join(paragraphs)


def _sentence_for(entry: GapAnalysisEntry, index: int) -> str:
    phrase = NATURAL_PHRASING.get(entry.requirement, entry.requirement.lower())
    snippet = _clean_snippet_for_prose(entry.evidence_snippet)

    # If the snippet itself already starts with the phrase (e.g. a CV
    # skills entry literally reading "Excel (advanced)"), the normal
    # "phrase: snippet" template would produce an awkward echo like
    # "Excel: Excel (advanced)". Use a template that doesn't repeat the
    # phrase name in that case.
    redundant = snippet.lower().startswith(phrase.lower())

    if entry.message_type == GapMessageType.HAS_SKILL:
        if redundant:
            return f"My CV lists {snippet.rstrip('.')} as a skill I use regularly."
        template = _HAS_SKILL_TEMPLATES[index % len(_HAS_SKILL_TEMPLATES)]
    elif entry.message_type == GapMessageType.TRANSFERABLE_EVIDENCE:
        template = _TRANSFERABLE_TEMPLATES[index % len(_TRANSFERABLE_TEMPLATES)]
    else:  # NEEDS_STRONGER_EVIDENCE
        template = _NEEDS_STRONGER_TEMPLATES[index % len(_NEEDS_STRONGER_TEMPLATES)]

    return template.format(
        phrase=phrase,
        phrase_cap=phrase[:1].upper() + phrase[1:],
        snippet=snippet,
        snippet_lower=snippet[:1].lower() + snippet[1:],
    )


def _clean_snippet_for_prose(snippet: str) -> str:
    """
    evidence_snippet may carry a leading bullet marker (e.g. "- Built and
    maintained...") which reads fine in a table row but looks broken
    embedded mid-sentence (e.g. "directly — - Designed a..."). Strip it
    for prose use; the matrix/table display elsewhere keeps the original,
    unmodified snippet.
    """
    cleaned = re.sub(r"^[-•*▪●○]\s*", "", snippet.strip())
    return cleaned.rstrip(".") + "."


def _top_phrases(entries: list[GapAnalysisEntry], count: int) -> list[str]:
    phrases = [NATURAL_PHRASING.get(e.requirement, e.requirement.lower()) for e in entries[:count]]
    return phrases


def _join_phrases(phrases: list[str]) -> str:
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1]) + f", and {phrases[-1]}"


def _frequency_ratio(entry: GapAnalysisEntry) -> float:
    try:
        numerator, denominator = entry.jd_frequency.split("/")
        denominator_int = int(denominator)
        if denominator_int == 0:
            return 0.0
        return int(numerator) / denominator_int
    except (ValueError, AttributeError):
        return 0.0
