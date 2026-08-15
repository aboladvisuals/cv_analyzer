"""
job_parser.py

Parses ONE job description into a structured set of requirements, tagged
by how they were framed in the original text:

  - required        (essential / must-have)
  - preferred        (desirable / nice-to-have)
  - responsibility   (a duty of the role — not the same as a "requirement")
  - competency        (behavioural framing, common in NHS/Civil Service ads)

This module deliberately does the SAME job whether it's parsing the single
"target job description" or one of several "similar job descriptions" —
similar_jobs.py (next module) is what handles the multi-JD orchestration
and calls this function once per JD.

Like cv_parser.py, this is rule-based (regex + header/phrase matching),
not a machine-learning classifier. It won't be perfect on every JD layout,
but every category it assigns is traceable back to the text that produced
it, which matters for the "explain every score" requirement later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from config import RequirementCategory


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class ParsedRequirement:
    text: str               # the requirement/phrase itself, cleaned up
    category: str           # one of RequirementCategory's constants
    source_line: str        # the original line it came from, for traceability


@dataclass
class JobParseResult:
    is_valid: bool
    raw_text: str = ""
    requirements: list[ParsedRequirement] = field(default_factory=list)
    error: str = ""

    def by_category(self, category: str) -> list[ParsedRequirement]:
        return [r for r in self.requirements if r.category == category]


# ---------------------------------------------------------------------------
# Section headers that tell us how to categorise everything under them.
# Order matters slightly: more specific phrases are listed before more
# generic ones so exact matches win.
# ---------------------------------------------------------------------------

SECTION_TO_CATEGORY: dict[str, str] = {
    # Required / essential
    "essential criteria": RequirementCategory.REQUIRED,
    "essential requirements": RequirementCategory.REQUIRED,
    "required skills": RequirementCategory.REQUIRED,
    "requirements": RequirementCategory.REQUIRED,
    "must have": RequirementCategory.REQUIRED,
    "person specification": RequirementCategory.REQUIRED,
    # Preferred / desirable
    "desirable criteria": RequirementCategory.PREFERRED,
    "desirable requirements": RequirementCategory.PREFERRED,
    "preferred skills": RequirementCategory.PREFERRED,
    "nice to have": RequirementCategory.PREFERRED,
    "preferred qualifications": RequirementCategory.PREFERRED,
    # Responsibilities
    "responsibilities": RequirementCategory.RESPONSIBILITY,
    "key responsibilities": RequirementCategory.RESPONSIBILITY,
    "duties": RequirementCategory.RESPONSIBILITY,
    "what you'll do": RequirementCategory.RESPONSIBILITY,
    "main duties": RequirementCategory.RESPONSIBILITY,
    # Competencies / behaviours (common in NHS / Civil Service adverts)
    "competencies": RequirementCategory.COMPETENCY,
    "behaviours": RequirementCategory.COMPETENCY,
    "behaviors": RequirementCategory.COMPETENCY,
    "core values": RequirementCategory.COMPETENCY,
    "values and behaviours": RequirementCategory.COMPETENCY,
}

# A line that starts a bullet — used to split a section's body into
# individual requirement items rather than treating the whole section as
# one giant blob of text.
_BULLET_PREFIX = re.compile(r"^\s*[-•*▪●○]\s*|\s*^\d+[\.\)]\s*")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_job_description(text: str) -> JobParseResult:
    """
    Parse raw job description text into categorised requirements.

    `text` is expected to already be clean text (e.g. pasted by the user,
    or extracted upstream) — this module doesn't do file I/O; that keeps
    it usable for both the target JD and every similar JD without caring
    where the text came from.
    """
    if not text or not text.strip():
        return JobParseResult(is_valid=False, error="Job description text is empty.")

    cleaned = _clean_text(text)
    requirements = _extract_requirements(cleaned)

    if not requirements:
        # We still return is_valid=True with zero requirements rather than
        # failing outright — a very short or unusually formatted JD isn't
        # necessarily invalid, just harder to parse. Downstream code can
        # decide how to handle "zero requirements found".
        return JobParseResult(is_valid=True, raw_text=cleaned, requirements=[])

    return JobParseResult(is_valid=True, raw_text=cleaned, requirements=requirements)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _extract_requirements(text: str) -> list[ParsedRequirement]:
    lines = text.split("\n")
    results: list[ParsedRequirement] = []
    current_category: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        header_category = _match_section_header(stripped)
        if header_category:
            current_category = header_category
            continue

        if current_category is None:
            # We haven't hit a recognised section yet — skip intro/preamble
            # text (company blurb, greeting, etc.) rather than mis-filing
            # it as a requirement.
            continue

        item_text = _strip_bullet(stripped)
        if item_text:
            results.append(
                ParsedRequirement(
                    text=item_text,
                    category=current_category,
                    source_line=stripped,
                )
            )

    return results


def _match_section_header(line: str) -> str | None:
    """
    Returns the RequirementCategory this line's header maps to, or None
    if the line isn't a recognised section header. Headers are matched on
    their own line, optionally followed by a colon — same approach as
    cv_parser.py's section detection, kept consistent deliberately.
    """
    candidate = line.rstrip(":").lower()
    return SECTION_TO_CATEGORY.get(candidate)


def _strip_bullet(line: str) -> str:
    """Remove a leading bullet/number marker, e.g. '- SQL' -> 'SQL'."""
    return _BULLET_PREFIX.sub("", line, count=1).strip()
