"""
tests/test_frequency_analyser.py

Tests for frequency_analyser.py, using the sample target JD + 3 sample
similar JDs (all fictional NHS-style Data Analyst adverts). Covers:
  - correct frequency fractions (e.g. SQL appears in all 3 similar JDs)
  - a phrase's target-JD category is attached correctly
  - a phrase that appears in similar JDs but NOT the target JD is still
    reported (never silently dropped)
  - frequency is reported as a fact, not converted into an "importance"
    label anywhere in this module
"""

import config
import similar_jobs
import frequency_analyser
from config import RequirementCategory


TARGET_JD_PATH = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"
SIMILAR_JD_PATHS = [
    config.SAMPLE_DATA_DIR / "sample_jd_similar_1.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_2.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_3.txt",
]


def _build_result():
    target_text = TARGET_JD_PATH.read_text(encoding="utf-8")
    similar_texts = [p.read_text(encoding="utf-8") for p in SIMILAR_JD_PATHS]
    similar_result = similar_jobs.analyse_similar_jobs(target_text, similar_texts)
    return frequency_analyser.analyse_frequency(similar_result)


def test_sql_appears_in_all_similar_jds():
    result = _build_result()
    entry = result.entry_for("SQL")

    assert entry is not None
    assert entry.similar_jd_total == 3
    assert entry.similar_jd_count == 3
    assert entry.frequency_fraction == "3/3"
    assert entry.frequency_ratio == 1.0


def test_target_jd_category_is_attached():
    result = _build_result()
    sql_entry = result.entry_for("SQL")
    python_entry = result.entry_for("Python")

    assert sql_entry.target_jd_category == RequirementCategory.REQUIRED
    assert sql_entry.in_target_jd

    assert python_entry.target_jd_category == RequirementCategory.PREFERRED
    assert python_entry.in_target_jd


def test_phrase_missing_from_target_jd_is_still_reported_if_in_similar_jds():
    result = _build_result()
    # "Attention to detail" appears in similar_jd_1's Competencies section
    # but is not phrased that way in the target JD sample — confirms we
    # don't drop phrases just because the target JD didn't use them.
    entry = result.entry_for("Attention to detail")

    assert entry is not None
    assert entry.similar_jd_count >= 1
    assert entry.target_jd_category is None
    assert not entry.in_target_jd


def test_frequency_entries_do_not_carry_an_importance_label():
    result = _build_result()
    for entry in result.entries:
        # FrequencyEntry should only expose factual fields — frequency
        # counts and category framing — never a derived "importance"
        # verdict. This guards against that logic creeping in here
        # instead of staying in gap_analyser.py (a later module).
        assert not hasattr(entry, "importance")
        assert not hasattr(entry, "priority")


def test_sorted_by_frequency_is_descending():
    result = _build_result()
    sorted_entries = result.sorted_by_frequency()

    counts = [e.similar_jd_count for e in sorted_entries]
    assert counts == sorted(counts, reverse=True)
