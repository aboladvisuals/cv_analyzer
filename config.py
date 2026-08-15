"""
config.py

Central configuration for the CV Analyzer & Job Match Optimizer.

Why this file exists:
    Rather than scattering "magic numbers" and settings across the codebase,
    we keep everything that might reasonably change (scoring weights, file
    size limits, supported formats) in ONE place. Later phases will import
    from here instead of hard-coding values.

This is Phase 1: only the settings needed for the project to exist and run
are defined for real. Settings that later phases will use (e.g. AI provider
config) are stubbed in now so the shape of the config is visible early.
"""

from dataclasses import dataclass, field
from pathlib import Path
import os

# Load a local .env file if one exists next to this project (e.g.
# CV_ANALYZER_AI_ENABLED=true, CV_ANALYZER_API_KEY=..., etc.). This is a
# no-op if no .env file is present, so it's always safe to call. Doing
# this here, at the top of config.py, means every other module that
# reads AI settings via os.getenv() below picks up .env values
# automatically without needing to call load_dotenv() itself.
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

# BASE_DIR = the cv_analyser/ folder itself, regardless of where the app is
# run from. Using __file__ like this avoids "it works on my machine" bugs
# caused by relative paths.
BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
BENCHMARKS_DIR = DATA_DIR / "benchmarks"
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"


# ---------------------------------------------------------------------------
# Scoring weights (configurable, not hard-coded permanently)
# ---------------------------------------------------------------------------
# These will be used starting in Phase 6 (scoring engine), but we define the
# structure now so the whole project has one authoritative source for it.
# Weights must sum to 1.0 (i.e. 100%).

@dataclass
class ScoringWeights:
    required_skills: float = 0.30
    experience: float = 0.25
    keyword_match: float = 0.15
    industry_relevance: float = 0.10
    evidence_achievements: float = 0.10
    cv_structure: float = 0.05
    education_certifications: float = 0.05

    def as_dict(self) -> dict:
        return {
            "required_skills": self.required_skills,
            "experience": self.experience,
            "keyword_match": self.keyword_match,
            "industry_relevance": self.industry_relevance,
            "evidence_achievements": self.evidence_achievements,
            "cv_structure": self.cv_structure,
            "education_certifications": self.education_certifications,
        }

    def validate(self) -> None:
        total = sum(self.as_dict().values())
        if not (0.999 <= total <= 1.001):  # tolerate floating point drift
            raise ValueError(
                f"Scoring weights must sum to 1.0 (100%). Currently sum to {total}."
            )


DEFAULT_SCORING_WEIGHTS = ScoringWeights()
DEFAULT_SCORING_WEIGHTS.validate()


# ---------------------------------------------------------------------------
# File handling
# ---------------------------------------------------------------------------

SUPPORTED_CV_FORMATS = (".pdf", ".docx", ".txt")
MAX_CV_FILE_SIZE_MB = 10


# ---------------------------------------------------------------------------
# Multi-job-description analysis (added for the evidence-based personal
# statement feature — builds on Phase 1, does not change it)
# ---------------------------------------------------------------------------
# The user should provide several similar job descriptions for the same/
# similar role so recurring requirements can be identified, rather than
# tailoring everything to a single advert. 10 is the *recommended* number,
# not a hard requirement — anywhere from MIN_SIMILAR_JDS upward is accepted.

MIN_SIMILAR_JDS = 5
RECOMMENDED_SIMILAR_JDS = 10


class RequirementCategory:
    """
    How a mined requirement was framed in its source job description.
    Kept as plain string constants (not an Enum) so they serialise cleanly
    to JSON/dict output without extra handling in later phases.
    """
    REQUIRED = "required"          # explicitly essential/must-have
    PREFERRED = "preferred"        # desirable/nice-to-have
    RESPONSIBILITY = "responsibility"  # a duty of the role, not a "requirement" per se
    COMPETENCY = "competency"      # behavioural/soft-skill framing (common in NHS/Civil Service)


class EvidenceStatus:
    """
    The outcome of comparing a mined requirement against a candidate's CV.
    Deliberately distinct categories so the app never collapses "candidate
    has this" and "candidate should consider developing this" into one thing.
    """
    STRONG_MATCH = "strong_match"          # clear, direct evidence in the CV
    PARTIAL_MATCH = "partial_match"        # related evidence, not a full match
    TRANSFERABLE = "transferable"          # different context, genuinely relevant evidence
    MISSING = "missing"                    # no evidence found — never fabricated


class StatementTier:
    """
    The three levels of personal statement, from most reusable to most
    specific. Each tier is generated by the same personal_statement.py
    logic, parameterised by which tier is requested.
    """
    MASTER = "master"        # reusable across employers for the same role
    INDUSTRY = "industry"    # Master adapted toward one industry/sector
    VACANCY = "vacancy"      # tailored to one specific job description


class GapPriority:
    """
    How urgently a gap is worth the candidate's attention. Deliberately
    based on how the TARGET job description itself framed the
    requirement (required vs preferred vs responsibility/competency),
    not on raw cross-JD frequency — frequency tells you how common a
    requirement is across the market, not how important it is for THIS
    vacancy, and the two must not be conflated (see gap_analyser.py).
    """
    HIGH = "high"       # required in the target JD, evidence missing
    MEDIUM = "medium"   # required-but-partial, or preferred-but-missing
    LOW = "low"         # preferred/responsibility/competency, weaker stakes
    NONE = "none"       # not a gap — strong evidence already exists


# ---------------------------------------------------------------------------
# AI / LLM integration (stub for now — used from Phase 8/9 onward)
# ---------------------------------------------------------------------------
# We read from environment variables so no secrets are ever hard-coded or
# committed to source control. python-dotenv (added later) will let a local
# .env file populate these during development.

AI_ENABLED = os.getenv("CV_ANALYZER_AI_ENABLED", "false").lower() == "true"
AI_API_KEY = os.getenv("CV_ANALYZER_API_KEY", "")
AI_API_BASE_URL = os.getenv("CV_ANALYZER_API_BASE_URL", "")
AI_MODEL_NAME = os.getenv("CV_ANALYZER_MODEL_NAME", "")


# ---------------------------------------------------------------------------
# Application metadata
# ---------------------------------------------------------------------------

APP_NAME = "CV Analyzer & Job Match Optimizer"
APP_VERSION = "0.1.0"  # Phase 1 — project foundation
