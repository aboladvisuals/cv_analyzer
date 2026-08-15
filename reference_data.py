"""
reference_data.py

Optional, SUPPLEMENTARY context about country and industry conventions —
NOT part of the evidence-matching engine, and NEVER used to score,
match, or judge a CV. This directly implements the brief's own
instruction: don't pretend there's one universal CV standard for a
country or industry; provide general contextual guidance, stored as
editable reference data, with the job description always remaining the
strongest source of truth.

This module never feeds into evidence_mapper.py, gap_analyser.py, or
personal_statement.py — it's a separate, clearly-labelled "for context"
panel a user can optionally read alongside the real, evidence-based
analysis. Nothing here is generated on the fly from general knowledge at
request time; it's fixed, reviewable, editable data.

Reference data lives as JSON files under:
    data/benchmarks/countries/*.json
    data/benchmarks/industries/*.json

Adding or correcting a country/industry means editing a JSON file, not
touching code. Each file has the shape:
    {
      "name": "United Kingdom",
      "key_conventions": ["...", "..."],
      "regulatory_considerations": ["...", "..."],
      "terminology_notes": ["...", "..."],
      "source_note": "..."   (optional — defaults to GENERAL_DISCLAIMER)
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

import config


GENERAL_DISCLAIMER = (
    "This is general background information only, not a rule followed by "
    "every employer in this country or industry. The specific job "
    "description always takes priority over anything shown here."
)


@dataclass
class ReferenceInfo:
    name: str
    key_conventions: list[str] = field(default_factory=list)
    regulatory_considerations: list[str] = field(default_factory=list)
    terminology_notes: list[str] = field(default_factory=list)
    source_note: str = GENERAL_DISCLAIMER


def list_available_countries() -> list[str]:
    return _list_available("countries")


def list_available_industries() -> list[str]:
    return _list_available("industries")


def load_country_reference(country_name: str) -> ReferenceInfo | None:
    return _load_reference("countries", country_name)


def load_industry_reference(industry_name: str) -> ReferenceInfo | None:
    return _load_reference("industries", industry_name)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _reference_dir(kind: str) -> Path:
    return config.BENCHMARKS_DIR / kind


def _list_available(kind: str) -> list[str]:
    directory = _reference_dir(kind)
    if not directory.exists():
        return []
    names: list[str] = []
    for path in sorted(directory.glob("*.json")):
        data = _read_json(path)
        if data is not None:
            names.append(data.get("name", path.stem))
    return names


def _load_reference(kind: str, name: str) -> ReferenceInfo | None:
    if not name or not name.strip():
        return None

    directory = _reference_dir(kind)
    if not directory.exists():
        return None

    target = name.strip().lower()
    for path in sorted(directory.glob("*.json")):
        data = _read_json(path)
        if data is None:
            continue
        candidate_name = data.get("name", "")
        # Match on the human-readable "name" field OR the filename itself
        # (e.g. "united_kingdom.json" matches "united kingdom"), so a
        # lookup works whether the caller typed the display name or
        # something close to the file's slug.
        if candidate_name.strip().lower() == target or path.stem.lower() == target.replace(" ", "_"):
            return ReferenceInfo(
                name=candidate_name or path.stem,
                key_conventions=data.get("key_conventions", []),
                regulatory_considerations=data.get("regulatory_considerations", []),
                terminology_notes=data.get("terminology_notes", []),
                source_note=data.get("source_note", GENERAL_DISCLAIMER),
            )
    return None


def _read_json(path: Path) -> dict | None:
    # Never let one malformed reference file take down the whole lookup —
    # skip it and keep going, same "don't crash on bad input" discipline
    # as cv_parser.py and job_parser.py.
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
