"""
similar_jobs.py

Takes the ONE target job description plus a collection of "similar" job
descriptions (same or closely related role, different employers) and runs
job_parser.py across all of them.

This module deliberately does NOT calculate frequency itself — that is
frequency_analyser.py's job. similar_jobs.py's only responsibility is:
  1. Parse the target JD and every similar JD.
  2. Track how many similar JDs were actually usable (some might fail to
     parse — e.g. empty paste — and we don't want the app to silently
     pretend those didn't happen).
  3. Warn (but not block) when the user provides fewer than
     config.MIN_SIMILAR_JDS.

Keeping this separate from job_parser.py means job_parser.py stays a
"parse ONE JD" tool that's simple to test and reason about, while this
module handles the "here are several JDs" orchestration on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import config
import job_parser
from job_parser import JobParseResult


@dataclass
class SimilarJobsResult:
    target_jd: JobParseResult
    similar_jds: list[JobParseResult] = field(default_factory=list)
    similar_jds_requested: int = 0
    similar_jds_parsed: int = 0
    warning: str = ""

    @property
    def meets_recommended_count(self) -> bool:
        return self.similar_jds_parsed >= config.RECOMMENDED_SIMILAR_JDS

    @property
    def meets_minimum_count(self) -> bool:
        return self.similar_jds_parsed >= config.MIN_SIMILAR_JDS


def analyse_similar_jobs(target_jd_text: str, similar_jd_texts: list[str]) -> SimilarJobsResult:
    """
    Parse the target job description and a list of similar job description
    texts. Returns a SimilarJobsResult that downstream modules
    (frequency_analyser.py, evidence_mapper.py) can consume.

    `similar_jd_texts` should be a list of raw text strings — one per
    similar job advert. Each is parsed independently with job_parser, so
    a malformed entry in the middle of the list doesn't stop the others
    from being processed.
    """
    target_result = job_parser.parse_job_description(target_jd_text)

    similar_results: list[JobParseResult] = []
    for jd_text in similar_jd_texts:
        result = job_parser.parse_job_description(jd_text)
        similar_results.append(result)

    parsed_count = sum(1 for r in similar_results if r.is_valid and r.requirements)
    requested_count = len(similar_jd_texts)

    warning = _build_warning(requested_count, parsed_count)

    return SimilarJobsResult(
        target_jd=target_result,
        similar_jds=similar_results,
        similar_jds_requested=requested_count,
        similar_jds_parsed=parsed_count,
        warning=warning,
    )


def _build_warning(requested_count: int, parsed_count: int) -> str:
    """
    Builds a human-readable warning when the usable similar-JD count falls
    below what's recommended or required. Returns "" when there's nothing
    to warn about — callers can check `if result.warning:` cleanly.

    This never blocks analysis — config.MIN_SIMILAR_JDS is guidance, not
    a hard requirement, per the original brief ("do NOT hard-code exactly
    10 as a universal requirement").
    """
    if parsed_count == 0:
        return (
            "No similar job descriptions could be parsed. Frequency analysis "
            "will be skipped — only the target job description will be used."
        )
    if parsed_count < config.MIN_SIMILAR_JDS:
        return (
            f"Only {parsed_count} similar job description(s) were usable "
            f"(out of {requested_count} provided). For more reliable "
            f"frequency analysis, {config.MIN_SIMILAR_JDS}-"
            f"{config.RECOMMENDED_SIMILAR_JDS} is recommended, but the "
            f"analysis will proceed with what's available."
        )
    if parsed_count < config.RECOMMENDED_SIMILAR_JDS:
        return (
            f"{parsed_count} similar job descriptions were analysed. "
            f"{config.RECOMMENDED_SIMILAR_JDS} is the recommended number "
            f"for the most reliable frequency analysis, but this is "
            f"sufficient to proceed."
        )
    return ""
