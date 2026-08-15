"""
requirement_miner.py

job_parser.py gives us requirements as free text — e.g. "Proficient in SQL
for querying large datasets" and "Strong SQL skills" from two different
adverts. Those are the same underlying requirement, but as plain strings
they'd never match each other.

This module's job is to mine each ParsedRequirement down to canonical
phrases from a known vocabulary (e.g. both examples above -> "SQL"), so
frequency_analyser.py can count "how many JDs mention SQL" rather than
"how many JDs mention this exact sentence".

Design choice: matching is a curated phrase list + case-insensitive
substring search, not an ML/NLP model. That's a deliberate limitation for
this phase — it's transparent (every match traces back to a literal
phrase), testable, and has zero risk of "confidently" mismatching two
unrelated things. It will miss synonyms not in the list (e.g. "Business
Intelligence" not linked to "Power BI") — the vocabulary is meant to grow
over time, not be exhaustive on day one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from job_parser import JobParseResult, ParsedRequirement


@dataclass
class MinedRequirement:
    canonical_phrase: str      # the normalised term, e.g. "SQL"
    category: str              # RequirementCategory value, carried over from the source
    source_text: str           # the original requirement text it was mined from


# ---------------------------------------------------------------------------
# Known phrase vocabulary.
#
# Each canonical phrase maps to a list of surface forms we'll match against
# (case-insensitive). The canonical phrase itself is always included as a
# match target automatically, so it doesn't need to repeat itself here.
#
# This list is deliberately scoped to what's relevant for the Data
# Analyst / NHS / Civil Service test data this feature was built around.
# Extending it for other roles is just adding more entries — nothing else
# in this module needs to change.
# ---------------------------------------------------------------------------

KNOWN_PHRASES: dict[str, list[str]] = {
    "SQL": ["sql"],
    "Excel": ["excel", "pivot table"],
    "Power BI": ["power bi"],
    "Python": ["python"],
    "R": ["r for data", "r programming"],
    "Data visualisation": ["data visualisation", "data visualization"],
    "Dashboards": ["dashboard"],
    "Stakeholder communication": [
        "stakeholder", "communicate data", "communicating data",
        "present findings", "presenting findings", "non-technical",
    ],
    "Data quality": ["data quality"],
    "Healthcare/NHS data experience": [
        "nhs data", "nhs or healthcare", "healthcare setting", "healthcare data",
    ],
    "Degree-level education": [
        "degree level", "degree in a numerate", "bsc", "msc", "beng",
        "bachelor's degree", "bachelor degree", "undergraduate degree",
        "postgraduate degree", "honours degree",
    ],
    "Teamwork": ["teamwork", "collaboration", "collaborative"],
    "Continuous improvement": ["continuous improvement"],
    "Patient/public focus": ["patient", "public focus", "patient-centred", "patient-centered"],
    "Analytical thinking": ["analytical thinking", "analytical"],
    "Attention to detail": ["attention to detail"],
    "Performance reporting": ["performance report", "performance and quality report"],

    # -----------------------------------------------------------------
    # Expanded vocabulary — added to generalise beyond the original
    # Data Analyst / NHS test data, so the tool works reasonably for
    # other roles and industries without needing a rewrite.
    #
    # Naming discipline followed throughout: NEVER use a common,
    # standalone English word as a canonical phrase or surface form on
    # its own (e.g. bare "Go", bare "Lead", bare "Plan") — that was the
    # exact class of bug found earlier with the single-letter phrase
    # "R" wrongly matching almost any text. Every short/ambiguous term
    # below is anchored with enough surrounding context (e.g. "go
    # programming" not "go") that ordinary sentences won't trip it.
    # -----------------------------------------------------------------

    # Additional data/analytics tools
    "Tableau": ["tableau"],
    "Looker": ["looker"],
    "Qlik": ["qlik", "qlikview", "qlik sense"],
    "SAS": ["sas programming", "sas software"],
    "Google Analytics": ["google analytics"],
    "A/B testing": ["a/b testing", "ab testing"],
    "Machine learning": ["machine learning", "ml model"],
    "Statistical analysis": ["statistical analysis", "statistics"],
    "Data warehousing": ["data warehouse", "data warehousing"],
    "ETL": ["etl", "extract transform load"],

    # Software engineering / general technical
    "Git": ["git", "version control"],
    "AWS": ["aws", "amazon web services"],
    "Microsoft Azure": ["azure cloud", "microsoft azure"],
    "Google Cloud Platform": ["gcp", "google cloud platform", "google cloud"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "SQL Server": ["sql server", "mssql"],
    "Java programming": ["java programming", "java developer"],
    "JavaScript": ["javascript"],
    "C programming": ["c programming", "c language"],
    "C++": ["c++"],
    "Go programming": ["golang", "go programming language"],
    "Salesforce": ["salesforce"],
    "SAP": ["sap system", "sap software"],
    "VBA": ["vba", "excel vba"],

    # Soft skills / competencies
    "Leadership": ["leadership", "led a team", "team lead"],
    "Project management": ["project management", "managed projects"],
    "Time management": ["time management"],
    "Problem solving": ["problem solving", "problem-solving"],
    "Mentoring": ["mentoring", "mentored", "coaching"],
    "Presentation skills": ["presentation skills", "presenting to"],
    "Negotiation": ["negotiation", "negotiating"],
    "Adaptability": ["adaptability", "adaptable"],
    "Customer service": ["customer service"],
    "Budget management": ["budget management", "managing budgets"],

    # Project methodologies
    # NOTE on "Agile": unlike the fixes above, this one is a deliberate,
    # documented trade-off rather than a clean fix. "Agile" methodology
    # is overwhelmingly written as the bare word "Agile" in real job
    # descriptions ("experience working in Agile environments"), so
    # requiring extra context (like "Java programming" does) would miss
    # the vast majority of genuine matches. The cost is that "Agile" can
    # also match ordinary soft-skill phrasing ("an agile, adaptable
    # thinker") that has nothing to do with the methodology. This is a
    # known, accepted limitation — not an oversight.
    "Agile": ["agile", "scrum", "kanban"],
    "PRINCE2": ["prince2"],
    "PMP": ["pmp certified", "project management professional"],

    # Compliance / governance
    "GDPR": ["gdpr", "data protection", "data privacy"],
    "Data governance": ["data governance"],

    # Early years / childcare / local government vocabulary
    # NOTE on naming: "SEND" is the standard UK acronym for Special
    # Educational Needs and Disabilities, but its lowercase form is also
    # the extremely common verb "send" — exactly the false-positive risk
    # already found with "Java" matching "cup of java". The canonical
    # name and every surface form below deliberately avoid the bare
    # word "send" for that reason.
    "EYFS": ["eyfs", "early years foundation stage"],
    "Safeguarding": ["safeguarding"],
    "Special educational needs (SEND)": [
        "special educational needs", "send coordinator", "senco",
    ],
    "Ofsted": ["ofsted"],
    "Child development": ["child development"],
    "Paediatric first aid": ["paediatric first aid", "pediatric first aid"],
    "DBS check": ["dbs check", "disclosure and barring service"],
    "Behaviour management": ["behaviour management", "behavior management"],
    "Parental engagement": [
        "parental engagement", "parent engagement", "parent and carer engagement",
    ],
    "Child protection": ["child protection"],
    "Multi-agency working": ["multi-agency working", "multi agency working"],
    "Level 3 childcare qualification": [
        "level 3 childcare", "cache level 3", "nvq level 3 childcare",
    ],
    # NOTE on "Key worker": in early years settings this specifically
    # means the practitioner assigned to a child's individual care —
    # not the broader "essential worker" sense from the pandemic era.
    # Two-word phrases carry much lower false-positive risk than bare
    # single words (see the "Agile" note above for the general
    # principle), so this is kept without further hedging.
    "Key worker (childcare)": ["key worker"],
    # NOTE on "Inclusive practice": deliberately includes bare
    # "inclusion" as a surface form, similar to the "Agile" trade-off —
    # "inclusion" is a common word in general diversity/equality
    # language too, not exclusively an early-years term. Accepted
    # because the alternative (requiring extra context) would miss most
    # genuine early-years mentions, which are very often just "inclusion".
    "Inclusive practice": ["inclusive practice", "inclusion"],
    "Local authority": ["local authority", "local government"],
    "Case management": ["case management"],
    "Social work": ["social work", "social worker"],
}


def mine_requirements(job_result: JobParseResult) -> list[MinedRequirement]:
    """
    Mine canonical phrases out of a single parsed job description's
    requirements. One ParsedRequirement can yield zero, one, or several
    MinedRequirement entries (e.g. "SQL and Power BI skills required"
    mentions two known phrases in one line).
    """
    if not job_result.is_valid:
        return []

    mined: list[MinedRequirement] = []
    for requirement in job_result.requirements:
        mined.extend(_mine_single_requirement(requirement))
    return mined


def _mine_single_requirement(requirement: ParsedRequirement) -> list[MinedRequirement]:
    """
    IMPORTANT: matching uses WORD-BOUNDARY regex, not plain substring
    search. Plain substring search has a real bug potential — e.g. the
    canonical phrase "R" as a raw substring would match inside "for",
    "or", "required", almost anywhere the letter appears; "Excel" would
    wrongly match inside "excellent". Word boundaries (\\b) ensure a
    phrase only matches as a whole word/phrase, not as a fragment of a
    longer, unrelated word.
    """
    text_lower = requirement.text.lower()
    matches: list[MinedRequirement] = []

    for canonical_phrase, surface_forms in KNOWN_PHRASES.items():
        all_forms = [canonical_phrase.lower(), *surface_forms]
        if any(_matches_as_whole_phrase(form, text_lower) for form in all_forms):
            matches.append(
                MinedRequirement(
                    canonical_phrase=canonical_phrase,
                    category=requirement.category,
                    source_text=requirement.text,
                )
            )

    return matches


def _matches_as_whole_phrase(form: str, text_lower: str) -> bool:
    """
    True if `form` appears in `text_lower` as a whole word/phrase, not as
    a fragment of a longer word. Surface forms in KNOWN_PHRASES may carry
    a leading/trailing space (e.g. " r for data") purely to disambiguate
    single-letter phrases during authoring — strip that before building
    the regex, since \\b already enforces the word boundary properly.

    This is a thin wrapper around phrase_in_text() so existing internal
    call sites don't need to change — phrase_in_text() is the public
    entry point other modules (evidence_mapper.py) should use.
    """
    return phrase_in_text(form, text_lower)


def phrase_in_text(phrase: str, text: str) -> bool:
    """
    Public, reusable whole-word/whole-phrase matcher. `text` is matched
    case-insensitively regardless of the case it's passed in.

    Hyphens and spaces are treated as equivalent (both normalised to a
    single space before matching) — otherwise a CV saying "data-quality
    issues" would fail to match the phrase "data quality" purely because
    of punctuation, which isn't a meaningful difference for this purpose.

    Shared by requirement_miner.py (matching JD requirement text against
    KNOWN_PHRASES) and evidence_mapper.py (matching those same canonical
    phrases against CV text) — keeping this in one place means both
    modules always agree on what counts as "SQL" appearing in a text,
    rather than risking two subtly different matching rules drifting
    apart over time.
    """
    cleaned = phrase.strip()
    if not cleaned:
        return False
    normalised_phrase = re.sub(r"[-\s]+", " ", cleaned.lower()).strip()
    normalised_text = re.sub(r"[-\s]+", " ", text.lower())
    pattern = r"\b" + re.escape(normalised_phrase) + r"\b"
    return re.search(pattern, normalised_text) is not None
