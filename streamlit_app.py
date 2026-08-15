"""
streamlit_app.py

Web UI for the CV Analyzer & Job Match Optimizer, built on Streamlit.

This file does NOT duplicate any analysis logic. Every button here calls
the same orchestration functions already used (and tested) by the CLI in
app.py — run_analysis(), generate_statement_package() — plus optimiser.py
and report_generator.py directly. This file's only job is presentation:
widgets in, results out.

Run with:
    streamlit run streamlit_app.py

(The CLI entry point, `python app.py`, is unaffected and still works —
this is a second, separate way to use the same tested engine.)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

import config
import app
import optimiser
import ai_phrasing
import reference_data
import report_generator
from config import StatementTier


st.set_page_config(page_title="CV Analyzer & Job Match Optimizer", layout="wide")


# ---------------------------------------------------------------------------
# Session state — Streamlit reruns the whole script on every interaction,
# so anything that needs to persist across reruns (the analysis results,
# generated statement, generated files) has to live in st.session_state.
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "bundle": None,
    "target_role": "",
    "country": "",
    "industry": "",
    "stmt_result": None,
    "quality_result": None,
    "optimisation_result": None,
    "docx_bytes": None,
    "pdf_bytes": None,
}
for _key, _default in _DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _default


st.title("CV Analyzer & Job Match Optimizer")

tab_analyse, tab_evidence, tab_statement, tab_optimise, tab_export = st.tabs(
    ["1. Analyse", "2. Evidence & Gaps", "3. Personal Statement", "4. CV Optimisation", "5. Export"]
)


# ---------------------------------------------------------------------------
# Tab 1 — Analyse
# ---------------------------------------------------------------------------

with tab_analyse:
    if st.button("Try the demo (Jordan Ellis's CV vs. an NHS Data Analyst role)"):
        cv_path = config.SAMPLE_DATA_DIR / "sample_cv_jordan_ellis.txt"
        target_path = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"
        similar_paths = [config.SAMPLE_DATA_DIR / f"sample_jd_similar_{i}.txt" for i in (1, 2, 3)]
        target_text_demo = target_path.read_text(encoding="utf-8")
        similar_texts_demo = [p.read_text(encoding="utf-8") for p in similar_paths]

        with st.spinner("Analysing demo data..."):
            bundle = app.run_analysis(str(cv_path), target_text_demo, similar_texts_demo)

        st.session_state.bundle = bundle
        st.session_state.target_role = "Data Analyst"
        st.session_state.country = ""
        st.session_state.industry = ""
        st.session_state.stmt_result = None
        st.session_state.quality_result = None
        st.session_state.optimisation_result = None
        st.session_state.docx_bytes = None
        st.session_state.pdf_bytes = None
        st.success("Demo data loaded and analysed — see the other tabs for results.")

    st.divider()

    st.header("1. Your CV")
    cv_input_mode = st.radio("How would you like to provide your CV?", ["Upload file", "Paste text"], horizontal=True)

    cv_source: str | None = None
    if cv_input_mode == "Upload file":
        uploaded_file = st.file_uploader("CV file", type=["pdf", "docx", "txt"])
        if uploaded_file is not None:
            suffix = Path(uploaded_file.name).suffix
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(uploaded_file.getvalue())
            tmp.close()
            cv_source = tmp.name
    else:
        pasted_cv = st.text_area("Paste your CV text", height=250)
        if pasted_cv.strip():
            cv_source = pasted_cv

    st.header("2. Target job")
    target_role_input = st.text_input("Target role (e.g. 'Data Analyst')")
    target_jd_text = st.text_area("Paste the target job description", height=200)

    with st.expander("Optional: country / industry context"):
        st.caption(
            "General background conventions only — never used in the evidence "
            "matrix or gap analysis. The job description above always remains "
            "the primary source of truth."
        )
        country_options = [""] + reference_data.list_available_countries()
        industry_options = [""] + reference_data.list_available_industries()
        country_input = st.selectbox("Country", country_options)
        industry_input = st.selectbox("Industry", industry_options)

    st.header(
        f"3. Similar job descriptions "
        f"(recommended: {config.MIN_SIMILAR_JDS}-{config.RECOMMENDED_SIMILAR_JDS})"
    )
    similar_count = st.number_input(
        "How many similar job descriptions will you provide?",
        min_value=0, max_value=15, value=0, step=1,
    )
    similar_texts: list[str] = []
    for i in range(int(similar_count)):
        text = st.text_area(f"Similar job description {i + 1}", height=150, key=f"similar_jd_{i}")
        if text.strip():
            similar_texts.append(text)

    if st.button("Run analysis", type="primary"):
        if not cv_source:
            st.error("Please provide a CV first.")
        elif not target_jd_text.strip():
            st.error("Please paste the target job description.")
        else:
            with st.spinner("Analysing..."):
                bundle = app.run_analysis(cv_source, target_jd_text, similar_texts)
            st.session_state.bundle = bundle
            st.session_state.target_role = target_role_input
            st.session_state.country = country_input
            st.session_state.industry = industry_input
            st.session_state.stmt_result = None
            st.session_state.quality_result = None
            st.session_state.optimisation_result = None
            st.session_state.docx_bytes = None
            st.session_state.pdf_bytes = None
            if bundle.cv_result.is_valid:
                st.success("Analysis complete — see the other tabs for results.")
            else:
                st.error(f"Could not read the CV: {bundle.cv_result.error}")


# ---------------------------------------------------------------------------
# Tab 2 — Evidence & Gaps
# ---------------------------------------------------------------------------

with tab_evidence:
    bundle = st.session_state.bundle
    if bundle is None:
        st.info("Run an analysis in the first tab to see results here.")
    elif not bundle.cv_result.is_valid:
        st.error(f"CV could not be read: {bundle.cv_result.error}")
    else:
        st.subheader("CV overview")
        detected_sections = [
            name.capitalize()
            for name in ("summary", "skills", "experience", "education", "certifications", "projects")
            if bundle.cv_result.section(name)
        ]
        st.write(
            f"Format: {bundle.cv_result.source_format.upper()} — "
            f"Sections detected: {', '.join(detected_sections) if detected_sections else 'None'}"
        )

        sj_result = bundle.similar_jobs_result
        st.write(
            f"Target JD parsed: {'Yes' if sj_result.target_jd.is_valid else 'No'}. "
            f"Similar JDs analysed: {sj_result.similar_jds_parsed} of {sj_result.similar_jds_requested}."
        )
        if sj_result.warning:
            st.warning(sj_result.warning)

        st.subheader("Evidence Matrix")
        matrix_rows = sorted(bundle.evidence_matrix.rows, key=lambda r: r.jd_frequency, reverse=True)
        table_data = [
            {
                "Requirement": row.requirement,
                "JD Frequency": row.jd_frequency,
                "Target JD": row.target_jd_category or "-",
                "CV Evidence": row.cv_evidence_label,
                "Source": row.evidence_source or "-",
            }
            for row in matrix_rows
        ]
        st.dataframe(table_data, use_container_width=True, hide_index=True)

        st.subheader("Gap Analysis Summary")
        gap_result = bundle.gap_result
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Strong matches", len(gap_result.strong_matches))
        col2.metric("Transferable", len(gap_result.transferable))
        col3.metric("Needs stronger evidence", len(gap_result.needs_stronger_evidence))
        col4.metric("Genuine gaps", len(gap_result.genuine_gaps))

        if gap_result.high_priority_gaps:
            st.error("High priority gaps:")
            for entry in gap_result.high_priority_gaps:
                st.write(f"- **{entry.requirement}**: {entry.message}")
        else:
            st.success("No high priority gaps — every required item has at least some evidence.")

        if gap_result.needs_stronger_evidence:
            st.warning("Needs stronger evidence:")
            for entry in gap_result.needs_stronger_evidence:
                st.write(f"- **{entry.requirement}**: {entry.message}")

        if gap_result.transferable:
            st.info("Transferable evidence:")
            for entry in gap_result.transferable:
                st.write(f"- **{entry.requirement}**: {entry.message}")

        with st.expander(f"Genuine gaps — no evidence found ({len(gap_result.genuine_gaps)})"):
            for entry in gap_result.genuine_gaps:
                st.write(f"- {entry.requirement}")

        country_ref = reference_data.load_country_reference(st.session_state.country)
        industry_ref = reference_data.load_industry_reference(st.session_state.industry)
        if country_ref or industry_ref:
            st.subheader("Country & Industry Context")
            st.caption(
                "General background only — never used in the evidence matrix "
                "or gap analysis above. The job description remains the "
                "primary source of truth."
            )
            for ref in (country_ref, industry_ref):
                if ref is None:
                    continue
                with st.expander(ref.name):
                    if ref.key_conventions:
                        st.write("**Common conventions:**")
                        for item in ref.key_conventions:
                            st.write(f"- {item}")
                    if ref.regulatory_considerations:
                        st.write("**Regulatory considerations:**")
                        for item in ref.regulatory_considerations:
                            st.write(f"- {item}")
                    if ref.terminology_notes:
                        st.write("**Terminology notes:**")
                        for item in ref.terminology_notes:
                            st.write(f"- {item}")
                    st.caption(ref.source_note)


# ---------------------------------------------------------------------------
# Tab 3 — Personal Statement
# ---------------------------------------------------------------------------

with tab_statement:
    bundle = st.session_state.bundle
    if bundle is None or not bundle.cv_result.is_valid:
        st.info("Run a valid analysis in the first tab first.")
    else:
        st.subheader("Generate a personal statement")
        role = st.text_input("Target role", value=st.session_state.target_role, key="stmt_role")
        tier_label = st.selectbox(
            "Statement type",
            [
                "Master (reusable across employers for this role)",
                "Industry (Master, adapted toward one industry)",
                "Vacancy (tailored to this specific job description)",
            ],
        )
        tier_map = {
            "Master (reusable across employers for this role)": StatementTier.MASTER,
            "Industry (Master, adapted toward one industry)": StatementTier.INDUSTRY,
            "Vacancy (tailored to this specific job description)": StatementTier.VACANCY,
        }
        tier = tier_map[tier_label]

        industry = None
        organisation = None
        structured = False
        if tier == StatementTier.INDUSTRY:
            industry = st.text_input("Industry (e.g. 'Healthcare')")
        elif tier == StatementTier.VACANCY:
            organisation = st.text_input("Organisation name (optional)") or None
            structured = st.checkbox(
                "Structured format — one heading per Essential/Desirable criterion "
                "(matches NHS/Civil Service application formats)"
            )

        max_words_input = st.number_input(
            "Maximum word count (0 for no limit)", min_value=0, value=0, step=50
        )
        max_words = int(max_words_input) or None

        if st.button("Generate statement", type="primary"):
            if not role.strip():
                st.error("Please enter a target role.")
            elif tier == StatementTier.INDUSTRY and not (industry or "").strip():
                st.error("Please enter an industry for an Industry-tier statement.")
            else:
                stmt_result, quality_result = app.generate_statement_package(
                    bundle.gap_result, target_role=role, tier=tier,
                    organisation=organisation, industry=industry,
                    structured=structured, max_words=max_words,
                )
                st.session_state.stmt_result = stmt_result
                st.session_state.quality_result = quality_result
                st.session_state.target_role = role
                st.session_state.docx_bytes = None  # stale — force regeneration on export
                st.session_state.pdf_bytes = None

        stmt_result = st.session_state.stmt_result
        quality_result = st.session_state.quality_result
        if stmt_result is not None:
            st.markdown(f"### {stmt_result.tier.capitalize()} Statement ({stmt_result.word_count} words)")
            st.write(stmt_result.statement_text)
            if stmt_result.trimmed_for_word_limit:
                st.info("Some lower-priority content was trimmed to fit the word limit.")
            if stmt_result.limitation_note:
                st.info(stmt_result.limitation_note)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Coverage", f"{quality_result.coverage_score * 100:.0f}%")
            c2.metric("Evidence", f"{quality_result.evidence_score * 100:.0f}%")
            c3.metric("Keyword relevance", f"{quality_result.keyword_relevance_score * 100:.0f}%")
            c4.metric("Natural language", f"{quality_result.natural_language_score * 100:.0f}%")

            with st.expander("Quality checklist"):
                for item in quality_result.checklist:
                    icon = "✅" if item.passed else "❌"
                    st.write(f"{icon} **{item.label}** — {item.detail}")
            st.caption(quality_result.summary_note)

            if ai_phrasing.is_ai_available():
                st.divider()
                st.caption(
                    "AI phrasing is available. Using it will send this statement's text "
                    "to an external AI API to rewrite it for more natural flow. It will "
                    "never add new claims — any response that appears to do so is "
                    "automatically rejected and the original wording is kept."
                )
                if st.button("Polish with AI"):
                    ai_result = ai_phrasing.polish_statement(stmt_result, bundle.gap_result)
                    if ai_result.used_ai:
                        stmt_result.statement_text = ai_result.polished_text
                        stmt_result.word_count = len(ai_result.polished_text.split())
                        st.session_state.docx_bytes = None
                        st.session_state.pdf_bytes = None
                        st.success("Statement polished with AI.")
                        st.rerun()
                    else:
                        st.warning(ai_result.error)


# ---------------------------------------------------------------------------
# Tab 4 — CV Optimisation
# ---------------------------------------------------------------------------

with tab_optimise:
    bundle = st.session_state.bundle
    if bundle is None or not bundle.cv_result.is_valid:
        st.info("Run a valid analysis in the first tab first.")
    else:
        if st.button("Get CV wording suggestions", type="primary"):
            st.session_state.optimisation_result = optimiser.generate_optimisation_suggestions(bundle.gap_result)
            st.session_state.docx_bytes = None
            st.session_state.pdf_bytes = None

        optimisation_result = st.session_state.optimisation_result
        if optimisation_result is not None:
            st.caption(optimisation_result.disclaimer)

            st.subheader(f"Suggested wording changes ({len(optimisation_result.suggestions)})")
            if not optimisation_result.suggestions:
                st.write("None — no genuine transferable evidence available to strengthen.")
            for i, suggestion in enumerate(optimisation_result.suggestions):
                with st.expander(f"{suggestion.requirement} ({suggestion.section} section)"):
                    st.write(f"**Original:** {suggestion.original_wording}")
                    st.write(f"**Proposed:** {suggestion.proposed_wording}")
                    st.write(f"**Reason:** {suggestion.reason}")
                    suggestion.approved = st.checkbox(
                        "Approve this wording change", key=f"approve_suggestion_{i}"
                    )

            st.subheader(f"Recommendations ({len(optimisation_result.recommendations)})")
            for rec in optimisation_result.recommendations:
                st.write(f"- **{rec.requirement}**: {rec.advice}")

            if optimisation_result.unaddressed_gaps:
                st.subheader("Not addressed")
                st.warning(
                    "No evidence in your CV for these — do not add them without genuine "
                    "experience: " + ", ".join(optimisation_result.unaddressed_gaps)
                )


# ---------------------------------------------------------------------------
# Tab 5 — Export
# ---------------------------------------------------------------------------

with tab_export:
    bundle = st.session_state.bundle
    if bundle is None or not bundle.cv_result.is_valid:
        st.info("Run a valid analysis in the first tab first.")
    else:
        st.subheader("Export this analysis as a report")
        st.caption(
            "Includes the evidence matrix and gap summary, plus your personal statement "
            "and optimisation suggestions if you generated them in the other tabs."
        )

        content = report_generator.build_report_content(
            bundle,
            target_role=st.session_state.target_role,
            stmt_result=st.session_state.stmt_result,
            quality_result=st.session_state.quality_result,
            optimisation_result=st.session_state.optimisation_result,
            country=st.session_state.country,
            industry=st.session_state.industry,
        )

        col_docx, col_pdf = st.columns(2)

        with col_docx:
            if st.button("Generate DOCX report"):
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
                tmp.close()
                report_generator.write_docx_report(content, tmp.name)
                st.session_state.docx_bytes = Path(tmp.name).read_bytes()

            if st.session_state.docx_bytes:
                st.download_button(
                    "Download DOCX report",
                    data=st.session_state.docx_bytes,
                    file_name="cv_analysis_report.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

        with col_pdf:
            if st.button("Generate PDF report"):
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                tmp.close()
                report_generator.write_pdf_report(content, tmp.name)
                st.session_state.pdf_bytes = Path(tmp.name).read_bytes()

            if st.session_state.pdf_bytes:
                st.download_button(
                    "Download PDF report",
                    data=st.session_state.pdf_bytes,
                    file_name="cv_analysis_report.pdf",
                    mime="application/pdf",
                )
