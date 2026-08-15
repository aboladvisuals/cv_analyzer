"""
ai_phrasing.py

Optional AI-assisted layer that rewrites a rule-based personal statement
for more natural phrasing. This is entirely optional — the application
is fully functional without it (see the original brief: "Do NOT make AI
mandatory for the first version"), and every call site must fall back to
the rule-based text if AI isn't configured, the request fails, or the
result fails a safety check.

CRITICAL CONSTRAINT: the AI is only ever asked to REPHRASE — never to add
new facts, skills, achievements, or experience. This is enforced two ways:
  1. The prompt sent to the model explicitly forbids adding new content.
  2. After the response comes back, _verify_no_fabrication() checks it
     against the SAME genuine-gap phrases gap_analyser.py already
     identified as having no CV evidence. If any of those phrases show
     up in the "polished" text, the AI output is REJECTED and the
     original rule-based text is used instead — a prompt instruction
     alone is not trusted as a safety guarantee.

No API key is ever hard-coded. Configuration comes entirely from
environment variables (optionally via a local .env file, loaded once in
config.py): CV_ANALYZER_AI_ENABLED, CV_ANALYZER_API_KEY,
CV_ANALYZER_API_BASE_URL, CV_ANALYZER_MODEL_NAME. The API is expected to
be OpenAI-compatible (a POST to {base_url}/chat/completions) — this
works with OpenAI itself, many hosted alternatives, and local servers
(e.g. Ollama, LM Studio) that expose the same interface.

Before this module is ever invoked, the calling code (app.py,
streamlit_app.py) must warn the user that using it sends their generated
statement text to an external API — this module does not show that
warning itself, since a library module should not assume how it's being
presented to the user.
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from gap_analyser import GapAnalysisResult
from personal_statement import PersonalStatementResult
from requirement_miner import phrase_in_text


@dataclass
class AIPhrasingResult:
    used_ai: bool
    original_text: str
    polished_text: str  # equals original_text whenever used_ai is False
    error: str = ""      # human-readable reason AI wasn't used, if applicable


_SYSTEM_PROMPT = (
    "You are a careful editor. You will be given a personal statement written "
    "for a job application. Rewrite it so it reads more naturally and flows "
    "better as prose, while strictly preserving its meaning.\n\n"
    "Hard rules — do not break these under any circumstances:\n"
    "1. Do NOT add any skill, qualification, achievement, employer, project, "
    "or experience that is not already explicitly stated in the original text.\n"
    "2. Do NOT change any factual detail — names, numbers, dates, employers, "
    "project names, or outcomes must stay exactly as given.\n"
    "3. Do NOT make the person sound more senior, more experienced, or more "
    "accomplished than the original text describes.\n"
    "4. Keep roughly the same length as the original.\n"
    "5. Output ONLY the rewritten statement text — no preamble, no notes, no "
    "explanation, no markdown formatting.\n\n"
    "If you are unsure whether a change would add new information, do not "
    "make that change."
)


def is_ai_available() -> bool:
    """
    True only when AI phrasing has been explicitly enabled AND an API key
    is present. Both must be set — a stray API key with the feature
    disabled should not silently start making network calls, and
    enabling the feature without a key can't do anything useful anyway.
    """
    return config.AI_ENABLED and bool(config.AI_API_KEY)


def polish_statement(
    stmt_result: PersonalStatementResult, gap_result: GapAnalysisResult
) -> AIPhrasingResult:
    """
    Attempts to produce a more naturally-phrased version of an already-
    generated statement. Always returns a result — never raises. Falls
    back to the original text (used_ai=False) whenever AI isn't
    configured, the request fails, or the response doesn't pass the
    fabrication safety check.
    """
    original_text = stmt_result.statement_text

    if not is_ai_available():
        return AIPhrasingResult(
            used_ai=False,
            original_text=original_text,
            polished_text=original_text,
            error=(
                "AI phrasing is not configured. Set CV_ANALYZER_AI_ENABLED=true "
                "and CV_ANALYZER_API_KEY (plus CV_ANALYZER_API_BASE_URL and "
                "CV_ANALYZER_MODEL_NAME) in a .env file to enable it."
            ),
        )

    try:
        polished_text = _call_ai_api(original_text)
    except Exception as exc:  # noqa: BLE001 — any network/API failure must
        # degrade gracefully to the rule-based text, never crash the app.
        return AIPhrasingResult(
            used_ai=False,
            original_text=original_text,
            polished_text=original_text,
            error=f"AI request failed ({exc}). Using the original wording instead.",
        )

    ok, reason = _verify_no_fabrication(original_text, polished_text, gap_result)
    if not ok:
        return AIPhrasingResult(
            used_ai=False,
            original_text=original_text,
            polished_text=original_text,
            error=f"AI output failed a safety check ({reason}). Using the original wording instead.",
        )

    return AIPhrasingResult(
        used_ai=True,
        original_text=original_text,
        polished_text=polished_text,
        error="",
    )


def _call_ai_api(text: str) -> str:
    """
    Isolated in its own function so tests can replace it (via
    unittest.mock.patch) instead of making a real network call. Raises
    on any failure — polish_statement() is responsible for catching that.
    """
    import requests

    response = requests.post(
        f"{config.AI_API_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.AI_API_KEY}"},
        json={
            "model": config.AI_MODEL_NAME,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.4,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def _verify_no_fabrication(
    original_text: str, polished_text: str, gap_result: GapAnalysisResult
) -> tuple[bool, str]:
    """
    The core safety check. Returns (ok, reason). Rejects the AI output if:
      - any genuine-gap requirement (one the candidate has NO CV evidence
        for) appears in the polished text — this would mean the AI added
        a claim the rule-based generator deliberately excluded.
      - the response is empty, or its length has drifted wildly from the
        original — a crude but effective guard against a degenerate
        response (e.g. an empty reply, or one that ballooned into
        unrelated content).
    """
    genuine_gap_phrases = {entry.requirement for entry in gap_result.genuine_gaps}
    for phrase in genuine_gap_phrases:
        if phrase_in_text(phrase, polished_text):
            return False, f"mentions '{phrase}', which has no evidence in the CV"

    if not polished_text.strip():
        return False, "empty response"

    original_word_count = max(len(original_text.split()), 1)
    polished_word_count = len(polished_text.split())
    ratio = polished_word_count / original_word_count
    if ratio < 0.5 or ratio > 2.0:
        return False, (
            f"length changed too much ({original_word_count} words -> "
            f"{polished_word_count} words)"
        )

    return True, ""
