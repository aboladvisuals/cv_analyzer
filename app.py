"""
app.py

Entry point for the CV Analyzer & Job Match Optimizer.

This file has two halves, kept deliberately separate:

1. ORCHESTRATION FUNCTIONS (run_analysis, generate_statement_package) —
   pure functions with no input()/print() calls. They take already-
   collected data in, and structured results out. This is what
   tests/test_app.py exercises directly — a CLI's interactive prompts
   can't sensibly be unit tested, but the logic they call absolutely
   should be, so that logic lives here instead of buried inside input()
   loops.

2. THE INTERACTIVE CLI (everything below "Interactive CLI") — thin
   wrappers around the orchestration functions that handle actually
   talking to the user: menus, prompts, and printing results.

CV optimisation offers reviewable suggestions ONLY — nothing is ever
applied to the CV automatically. The user approves or rejects each
suggestion individually; actually writing an edited CV file back out is
Export (a later phase, not yet built).
"""

from __future__ import annotations

from dataclasses import dataclass

import config
import cv_parser
import similar_jobs
import frequency_analyser
import evidence_mapper
import gap_analyser
import personal_statement
import statement_quality
import optimiser
import ai_phrasing
import reference_data
import report_generator
from analysis_bundle import AnalysisBundle
from cv_parser import CVParseResult
from similar_jobs import SimilarJobsResult
from frequency_analyser import FrequencyAnalysisResult
from evidence_mapper import EvidenceMatrixResult
from gap_analyser import GapAnalysisResult
from personal_statement import PersonalStatementInput, PersonalStatementResult
from statement_quality import StatementQualityResult
from optimiser import OptimisationResult
from config import StatementTier


# ---------------------------------------------------------------------------
# Orchestration functions (pure — no I/O, fully testable)
# ---------------------------------------------------------------------------

def run_analysis(
    cv_source: str, target_jd_text: str, similar_jd_texts: list[str] | None = None
) -> AnalysisBundle:
    """
    Runs the full pipeline: parse CV -> parse target + similar JDs ->
    mine frequency -> map evidence -> classify gaps.

    `similar_jd_texts` is optional. An empty list still produces a valid
    result — the target JD alone is analysed, just with zero cross-JD
    frequency data (this is what powers "Analyse CV + target job" mode,
    without needing separate logic from the full multi-JD mode).
    """
    similar_jd_texts = similar_jd_texts or []

    cv_result = cv_parser.parse_cv(cv_source)
    sj_result = similar_jobs.analyse_similar_jobs(target_jd_text, similar_jd_texts)
    freq_result = frequency_analyser.analyse_frequency(sj_result)
    matrix = evidence_mapper.build_evidence_matrix(cv_result, freq_result)
    gap_result = gap_analyser.analyse_gaps(matrix)

    return AnalysisBundle(
        cv_result=cv_result,
        similar_jobs_result=sj_result,
        frequency_result=freq_result,
        evidence_matrix=matrix,
        gap_result=gap_result,
    )


def generate_statement_package(
    gap_result: GapAnalysisResult,
    target_role: str,
    tier: str,
    organisation: str | None = None,
    industry: str | None = None,
    structured: bool = False,
    max_words: int | None = None,
) -> tuple[PersonalStatementResult, StatementQualityResult]:
    """Generates a personal statement at the given tier, then quality-checks it."""
    stmt_input = PersonalStatementInput(
        target_role=target_role, tier=tier, organisation=organisation, industry=industry,
        structured=structured, max_words=max_words,
    )
    stmt_result = personal_statement.generate_personal_statement(gap_result, stmt_input)
    quality_result = statement_quality.check_statement_quality(gap_result, stmt_result, stmt_input)
    return stmt_result, quality_result


# ---------------------------------------------------------------------------
# Display helpers (printing only — no logic, safe to change freely)
# ---------------------------------------------------------------------------

def print_cv_summary(cv_result: CVParseResult) -> None:
    print(f"\nCV parsed ({cv_result.source_format}): {'OK' if cv_result.is_valid else 'FAILED'}")
    if not cv_result.is_valid:
        print(f"  Error: {cv_result.error}")
        return
    for section_name in ("summary", "skills", "experience", "education", "certifications", "projects"):
        content = cv_result.section(section_name)
        status = "found" if content else "not detected"
        print(f"  - {section_name.capitalize():<15} {status}")


def print_similar_jobs_summary(sj_result: SimilarJobsResult) -> None:
    print(
        f"\nTarget job description parsed: "
        f"{'OK' if sj_result.target_jd.is_valid else 'FAILED'}"
    )
    print(f"Similar job descriptions analysed: {sj_result.similar_jds_parsed} "
          f"(of {sj_result.similar_jds_requested} provided)")
    if sj_result.warning:
        print(f"  Note: {sj_result.warning}")


def print_evidence_matrix(matrix: EvidenceMatrixResult) -> None:
    print(f"\n{'Requirement':<32} {'JD Freq':<8} {'Target JD':<12} {'CV Evidence':<13} {'Source':<12}")
    print("-" * 80)
    for row in sorted(matrix.rows, key=lambda r: r.jd_frequency, reverse=True):
        target_cat = row.target_jd_category or "-"
        print(f"{row.requirement:<32} {row.jd_frequency:<8} {target_cat:<12} "
              f"{row.cv_evidence_label:<13} {row.evidence_source or '-':<12}")


def print_gap_summary(gap_result: GapAnalysisResult) -> None:
    print("\n=== HIGH PRIORITY GAPS ===")
    if not gap_result.high_priority_gaps:
        print("  None — every required item has at least some evidence.")
    for entry in gap_result.high_priority_gaps:
        print(f"  - {entry.requirement}: {entry.message}")

    print("\n=== NEEDS STRONGER EVIDENCE ===")
    for entry in gap_result.needs_stronger_evidence:
        print(f"  - {entry.requirement}: {entry.message}")

    print("\n=== TRANSFERABLE EVIDENCE ===")
    for entry in gap_result.transferable:
        print(f"  - {entry.requirement}: {entry.message}")

    print(f"\nTotals: {len(gap_result.strong_matches)} strong match(es), "
          f"{len(gap_result.transferable)} transferable, "
          f"{len(gap_result.needs_stronger_evidence)} needing stronger evidence, "
          f"{len(gap_result.genuine_gaps)} genuine gap(s)")


def print_statement_package(
    stmt_result: PersonalStatementResult, quality_result: StatementQualityResult
) -> None:
    print(f"\n===== {stmt_result.tier.upper()} STATEMENT ({stmt_result.word_count} words) =====\n")
    print(stmt_result.statement_text)
    if stmt_result.trimmed_for_word_limit:
        print("\n[Note] Some lower-priority content was trimmed to fit the word limit.")
    if stmt_result.limitation_note:
        print(f"\n[Note] {stmt_result.limitation_note}")

    print(f"\nCoverage: {quality_result.coverage_score * 100:.0f}% | "
          f"Evidence: {quality_result.evidence_score * 100:.0f}% | "
          f"Keyword relevance: {quality_result.keyword_relevance_score * 100:.0f}% | "
          f"Natural language: {quality_result.natural_language_score * 100:.0f}%")
    print(f"All quality checks passed: {quality_result.all_checks_passed}")
    for item in quality_result.failed_checks():
        print(f"  Needs attention — {item.label}: {item.detail}")
    print(f"\n{quality_result.summary_note}")


def print_optimisation_result(result: OptimisationResult) -> None:
    print(f"\n{result.disclaimer}\n")

    print(f"=== SUGGESTED WORDING CHANGES ({len(result.suggestions)}) ===")
    if not result.suggestions:
        print("  None — no genuine transferable evidence available to strengthen.")
    for i, s in enumerate(result.suggestions, start=1):
        print(f"\n  [{i}] {s.requirement} ({s.section} section)")
        print(f"      Original: {s.original_wording}")
        print(f"      Proposed: {s.proposed_wording}")
        print(f"      Reason:   {s.reason}")

    print(f"\n=== RECOMMENDATIONS ({len(result.recommendations)}) ===")
    for r in result.recommendations:
        print(f"  - {r.requirement}: {r.advice}")

    if result.unaddressed_gaps:
        print(f"\n=== NOT ADDRESSED (no evidence in your CV — do not add without genuine experience) ===")
        for phrase in result.unaddressed_gaps:
            print(f"  - {phrase}")


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------

def _read_multiline(prompt: str) -> str:
    """
    Reads multi-line pasted text from the terminal until the user types
    END on its own line. This is the simplest reliable way to accept a
    pasted CV or job description in a plain terminal — input() itself
    only reads one line at a time.
    """
    print(f"{prompt}\n(Paste the text, then type END on its own line to finish.)")
    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def _collect_cv_source() -> str:
    choice = input(
        "\nHow would you like to provide the CV?\n"
        "  1) File path (.pdf, .docx, or .txt)\n"
        "  2) Paste the text directly\n"
        "Choice: "
    ).strip()
    if choice == "1":
        return input("File path: ").strip()
    return _read_multiline("Paste the CV text below.")


def _collect_similar_jds() -> list[str]:
    try:
        count = int(input(
            f"\nHow many similar job descriptions will you provide? "
            f"(recommended: {config.MIN_SIMILAR_JDS}-{config.RECOMMENDED_SIMILAR_JDS}): "
        ).strip())
    except ValueError:
        count = 0

    texts = []
    for i in range(count):
        texts.append(_read_multiline(f"Similar job description {i + 1}/{count}:"))
    return texts


def _maybe_generate_statement(
    gap_result: GapAnalysisResult,
) -> tuple[str, PersonalStatementResult | None, StatementQualityResult | None]:
    """Returns (target_role, stmt_result, quality_result) — target_role
    is returned even if the user declines a statement, so a later export
    step can still label the report correctly."""
    choice = input("\nGenerate a personal statement from this analysis? (y/n): ").strip().lower()
    if choice != "y":
        return "", None, None

    target_role = input("Target role (e.g. 'Data Analyst'): ").strip()
    tier_choice = input(
        "Statement type:\n"
        "  1) Master (reusable across employers for this role)\n"
        "  2) Industry (Master, adapted toward one industry)\n"
        "  3) Vacancy (tailored to this specific job description)\n"
        "Choice: "
    ).strip()

    tier_map = {"1": StatementTier.MASTER, "2": StatementTier.INDUSTRY, "3": StatementTier.VACANCY}
    tier = tier_map.get(tier_choice, StatementTier.MASTER)

    industry = None
    organisation = None
    structured = False
    if tier == StatementTier.INDUSTRY:
        industry = input("Industry (e.g. 'Healthcare'): ").strip()
    elif tier == StatementTier.VACANCY:
        organisation = input("Organisation name (optional, press Enter to skip): ").strip() or None
        format_choice = input(
            "Format:\n"
            "  1) Narrative (flowing prose)\n"
            "  2) Structured (one heading per Essential/Desirable criterion — "
            "matches NHS/Civil Service application formats)\n"
            "Choice: "
        ).strip()
        structured = format_choice == "2"

    max_words_input = input(
        "Maximum word count (optional, press Enter for no limit): "
    ).strip()
    max_words = int(max_words_input) if max_words_input.isdigit() else None

    stmt_result, quality_result = generate_statement_package(
        gap_result, target_role=target_role, tier=tier, organisation=organisation,
        industry=industry, structured=structured, max_words=max_words,
    )
    print_statement_package(stmt_result, quality_result)
    _maybe_polish_with_ai(stmt_result, gap_result)
    return target_role, stmt_result, quality_result


def _maybe_polish_with_ai(stmt_result: PersonalStatementResult, gap_result: GapAnalysisResult) -> None:
    if not ai_phrasing.is_ai_available():
        # Silent when AI isn't configured at all — most users won't have
        # set this up, and repeating "AI not configured" after every
        # statement would just be noise.
        return

    choice = input(
        "\nAI phrasing is available. Using it will send this statement's text "
        "to an external AI API to rewrite it for more natural flow (it will "
        "not add any new claims — see below if it does). Use it? (y/n): "
    ).strip().lower()
    if choice != "y":
        return

    result = ai_phrasing.polish_statement(stmt_result, gap_result)
    if result.used_ai:
        stmt_result.statement_text = result.polished_text
        stmt_result.word_count = len(result.polished_text.split())
        print("\n===== AI-POLISHED VERSION =====\n")
        print(result.polished_text)
    else:
        print(f"\n{result.error}")


def _maybe_offer_cv_optimisation(gap_result: GapAnalysisResult) -> optimiser.OptimisationResult | None:
    choice = input("\nGet CV wording suggestions from this analysis? (y/n): ").strip().lower()
    if choice != "y":
        return

    result = optimiser.generate_optimisation_suggestions(gap_result)
    print_optimisation_result(result)

    if not result.suggestions:
        return result

    print("\nReview each suggested wording change:")
    for i, suggestion in enumerate(result.suggestions, start=1):
        decision = input(
            f"\n[{i}] {suggestion.requirement} — approve this wording change? (y/n): "
        ).strip().lower()
        suggestion.approved = decision == "y"

    approved = result.approved_suggestions()
    print(f"\n{len(approved)} of {len(result.suggestions)} suggestion(s) approved.")
    if approved:
        print("(Nothing has been written to any file — apply these manually in your CV, "
              "or export a report below to keep a record of these suggestions.)")
    return result


def _maybe_show_reference_context() -> tuple[str, str]:
    """
    Optional country/industry conventions — purely supplementary, never
    fed into the evidence matrix or gap analysis. Returns the raw
    (country, industry) strings the user typed, whether or not a match
    was found, so the export step can still try the same lookup later.
    """
    country = input(
        "\nCountry for general contextual guidance (optional, press Enter to skip): "
    ).strip()
    industry = input(
        "Industry for general contextual guidance (optional, press Enter to skip): "
    ).strip()

    if country:
        ref = reference_data.load_country_reference(country)
        if ref:
            _print_reference_info(ref)
        else:
            available = ", ".join(reference_data.list_available_countries())
            print(f"No reference data for '{country}'. Available: {available}")

    if industry:
        ref = reference_data.load_industry_reference(industry)
        if ref:
            _print_reference_info(ref)
        else:
            available = ", ".join(reference_data.list_available_industries())
            print(f"No reference data for '{industry}'. Available: {available}")

    return country, industry


def _print_reference_info(ref: reference_data.ReferenceInfo) -> None:
    print(f"\n=== {ref.name} (general context) ===")
    if ref.key_conventions:
        print("Common conventions:")
        for item in ref.key_conventions:
            print(f"  - {item}")
    if ref.regulatory_considerations:
        print("Regulatory considerations:")
        for item in ref.regulatory_considerations:
            print(f"  - {item}")
    if ref.terminology_notes:
        print("Terminology notes:")
        for item in ref.terminology_notes:
            print(f"  - {item}")
    print(f"\n{ref.source_note}")


def _maybe_export_report(
    bundle: AnalysisBundle,
    target_role: str,
    stmt_result: PersonalStatementResult | None,
    quality_result: StatementQualityResult | None,
    optimisation_result: optimiser.OptimisationResult | None,
    country: str = "",
    industry: str = "",
) -> None:
    choice = input("\nExport this analysis as a report (DOCX/PDF)? (y/n): ").strip().lower()
    if choice != "y":
        return

    format_choice = input(
        "Format:\n  1) DOCX\n  2) PDF\n  3) Both\nChoice: "
    ).strip()
    filename = input(
        "File name, without extension (press Enter for 'cv_analysis_report'): "
    ).strip() or "cv_analysis_report"

    content = report_generator.build_report_content(
        bundle,
        target_role=target_role,
        stmt_result=stmt_result,
        quality_result=quality_result,
        optimisation_result=optimisation_result,
        country=country,
        industry=industry,
    )

    if format_choice in ("1", "3"):
        path = report_generator.write_docx_report(content, f"{filename}.docx")
        print(f"Saved: {path.resolve()}")
    if format_choice in ("2", "3"):
        path = report_generator.write_pdf_report(content, f"{filename}.pdf")
        print(f"Saved: {path.resolve()}")
    if format_choice not in ("1", "2", "3"):
        print("No valid format selected — nothing exported.")


def _run_demo() -> None:
    """Loads the built-in fictional sample data so the app can be tried
    end-to-end without typing anything in."""
    print("\nLoading sample data: Jordan Ellis's CV vs. an NHS Data Analyst role...")
    cv_path = config.SAMPLE_DATA_DIR / "sample_cv_jordan_ellis.txt"
    target_path = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"
    similar_paths = [
        config.SAMPLE_DATA_DIR / f"sample_jd_similar_{i}.txt" for i in (1, 2, 3)
    ]

    target_text = target_path.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in similar_paths]

    bundle = run_analysis(str(cv_path), target_text, similar_texts)
    print_cv_summary(bundle.cv_result)
    print_similar_jobs_summary(bundle.similar_jobs_result)
    print_evidence_matrix(bundle.evidence_matrix)
    print_gap_summary(bundle.gap_result)
    country, industry = _maybe_show_reference_context()
    target_role, stmt_result, quality_result = _maybe_generate_statement(bundle.gap_result)
    optimisation_result = _maybe_offer_cv_optimisation(bundle.gap_result)
    _maybe_export_report(
        bundle, target_role, stmt_result, quality_result, optimisation_result, country, industry
    )


def _run_interactive_analysis(include_similar_jds: bool) -> None:
    cv_source = _collect_cv_source()
    target_text = _read_multiline("Paste the target job description below.")
    similar_texts = _collect_similar_jds() if include_similar_jds else []

    bundle = run_analysis(cv_source, target_text, similar_texts)
    print_cv_summary(bundle.cv_result)
    if not bundle.cv_result.is_valid:
        return
    print_similar_jobs_summary(bundle.similar_jobs_result)
    print_evidence_matrix(bundle.evidence_matrix)
    print_gap_summary(bundle.gap_result)
    country, industry = _maybe_show_reference_context()
    target_role, stmt_result, quality_result = _maybe_generate_statement(bundle.gap_result)
    optimisation_result = _maybe_offer_cv_optimisation(bundle.gap_result)
    _maybe_export_report(
        bundle, target_role, stmt_result, quality_result, optimisation_result, country, industry
    )


def _run_cv_only() -> None:
    cv_source = _collect_cv_source()
    cv_result = cv_parser.parse_cv(cv_source)
    print_cv_summary(cv_result)


def main() -> None:
    print(f"{config.APP_NAME} — v{config.APP_VERSION}")
    print("-" * 50)

    while True:
        choice = input(
            "\nWhat would you like to do?\n"
            "  1) Analyse CV only\n"
            "  2) Analyse CV + target job description\n"
            "  3) Analyse CV + target job + similar job descriptions (recommended)\n"
            "  4) Try the demo (built-in sample data)\n"
            "  5) Exit\n"
            "Choice: "
        ).strip()

        if choice == "1":
            _run_cv_only()
        elif choice == "2":
            _run_interactive_analysis(include_similar_jds=False)
        elif choice == "3":
            _run_interactive_analysis(include_similar_jds=True)
        elif choice == "4":
            _run_demo()
        elif choice == "5":
            print("Goodbye.")
            break
        else:
            print("Please enter a number from 1 to 5.")


if __name__ == "__main__":
    main()
