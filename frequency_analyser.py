"""
frequency_analyser.py

Takes the output of similar_jobs.py (target JD + N similar JDs, each
already parsed) and requirement_miner.py (canonical phrases per JD), and
answers the question: "how often does each requirement show up across
the similar job descriptions?"

Example output shape (see FrequencyEntry):
    Power BI   — 3/4 similar JDs   — required in target JD
    SQL        — 4/4 similar JDs   — required in target JD
    NHS data   — 2/4 similar JDs   — preferred in target JD

IMPORTANT PRINCIPLE (directly from the brief): frequency alone is never
treated as proof of importance. This module reports frequency AND how the
requirement was framed (required/preferred/responsibility/competency) in
both the target JD and each similar JD — it does not collapse those into
a single "importance score". That judgement call is left to whatever
displays or consumes this data (later: gap_analyser.py / the UI).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import RequirementCategory
import requirement_miner
from requirement_miner import MinedRequirement
from similar_jobs import SimilarJobsResult


@dataclass
class FrequencyEntry:
    canonical_phrase: str
    similar_jd_count: int          # how many similar JDs mentioned this
    similar_jd_total: int          # how many similar JDs were analysed in total
    target_jd_category: str | None  # RequirementCategory value, or None if absent from target JD
    similar_jd_categories: list[str] = field(default_factory=list)  # one entry per similar JD that mentioned it

    @property
    def frequency_fraction(self) -> str:
        return f"{self.similar_jd_count}/{self.similar_jd_total}"

    @property
    def frequency_ratio(self) -> float:
        if self.similar_jd_total == 0:
            return 0.0
        return self.similar_jd_count / self.similar_jd_total

    @property
    def in_target_jd(self) -> bool:
        return self.target_jd_category is not None


@dataclass
class FrequencyAnalysisResult:
    entries: list[FrequencyEntry] = field(default_factory=list)
    similar_jds_analysed: int = 0

    def sorted_by_frequency(self) -> list[FrequencyEntry]:
        """Highest frequency first — the most common ordering for display."""
        return sorted(self.entries, key=lambda e: e.similar_jd_count, reverse=True)

    def entry_for(self, canonical_phrase: str) -> FrequencyEntry | None:
        for entry in self.entries:
            if entry.canonical_phrase == canonical_phrase:
                return entry
        return None


def analyse_frequency(similar_jobs_result: SimilarJobsResult) -> FrequencyAnalysisResult:
    """
    Build a FrequencyAnalysisResult from an already-parsed SimilarJobsResult.

    Only similar JDs that parsed successfully AND produced requirements
    are counted toward similar_jd_total — a JD we couldn't read shouldn't
    silently lower every phrase's apparent frequency.
    """
    usable_similar_jds = [
        jd for jd in similar_jobs_result.similar_jds if jd.is_valid and jd.requirements
    ]
    total = len(usable_similar_jds)

    # Mine the target JD separately — we need to know, per canonical
    # phrase, how IT framed the requirement (required/preferred/etc.),
    # since the target JD stays the primary source of truth.
    target_mined = requirement_miner.mine_requirements(similar_jobs_result.target_jd)
    target_category_by_phrase = _first_category_per_phrase(target_mined)

    # Mine every similar JD and track, per canonical phrase, which JDs
    # mentioned it and how they framed it.
    phrase_to_jd_categories: dict[str, list[str]] = {}
    for jd_result in usable_similar_jds:
        mined = requirement_miner.mine_requirements(jd_result)
        seen_phrases_this_jd: set[str] = set()
        for item in mined:
            # Count a phrase once per JD, even if mentioned multiple times
            # in the same advert (e.g. under both "Essential" and again
            # in "Responsibilities") — frequency is about how many JDs
            # raised it, not how many times it was repeated in one.
            if item.canonical_phrase in seen_phrases_this_jd:
                continue
            seen_phrases_this_jd.add(item.canonical_phrase)
            phrase_to_jd_categories.setdefault(item.canonical_phrase, []).append(item.category)

    # A phrase might appear only in the target JD and no similar JD (or
    # vice versa) — union both sets so nothing is silently dropped.
    all_phrases = set(phrase_to_jd_categories.keys()) | set(target_category_by_phrase.keys())

    entries = [
        FrequencyEntry(
            canonical_phrase=phrase,
            similar_jd_count=len(phrase_to_jd_categories.get(phrase, [])),
            similar_jd_total=total,
            target_jd_category=target_category_by_phrase.get(phrase),
            similar_jd_categories=phrase_to_jd_categories.get(phrase, []),
        )
        for phrase in sorted(all_phrases)
    ]

    return FrequencyAnalysisResult(entries=entries, similar_jds_analysed=total)


def _first_category_per_phrase(mined: list[MinedRequirement]) -> dict[str, str]:
    """
    If the target JD mentions the same phrase more than once under
    different headers (rare, but possible), we keep the FIRST category
    encountered rather than silently overwriting it — this keeps target
    JD categorisation deterministic and traceable.
    """
    result: dict[str, str] = {}
    for item in mined:
        result.setdefault(item.canonical_phrase, item.category)
    return result
