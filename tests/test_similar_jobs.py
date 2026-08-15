"""
tests/test_similar_jobs.py

Tests for similar_jobs.py. Covers:
  - parsing a target JD plus several similar JDs together
  - the warning logic for fewer than MIN_SIMILAR_JDS / RECOMMENDED_SIMILAR_JDS
  - a malformed/empty similar JD not stopping the others from being parsed
"""

import config
import similar_jobs


TARGET_JD_PATH = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"
SIMILAR_JD_PATHS = [
    config.SAMPLE_DATA_DIR / "sample_jd_similar_1.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_2.txt",
    config.SAMPLE_DATA_DIR / "sample_jd_similar_3.txt",
]


def _read(path):
    return path.read_text(encoding="utf-8")


def test_parses_target_and_similar_jds():
    target_text = _read(TARGET_JD_PATH)
    similar_texts = [_read(p) for p in SIMILAR_JD_PATHS]

    result = similar_jobs.analyse_similar_jobs(target_text, similar_texts)

    assert result.target_jd.is_valid
    assert len(result.similar_jds) == 3
    assert result.similar_jds_requested == 3
    assert result.similar_jds_parsed == 3
    assert all(jd.is_valid for jd in result.similar_jds)


def test_warns_when_below_minimum_similar_jds():
    target_text = _read(TARGET_JD_PATH)
    similar_texts = [_read(p) for p in SIMILAR_JD_PATHS]  # only 3, MIN is 5

    result = similar_jobs.analyse_similar_jobs(target_text, similar_texts)

    assert result.similar_jds_parsed < config.MIN_SIMILAR_JDS
    assert not result.meets_minimum_count
    assert result.warning != ""
    assert "recommended" in result.warning.lower() or "usable" in result.warning.lower()


def test_no_warning_when_recommended_count_met():
    target_text = _read(TARGET_JD_PATH)
    similar_text = _read(SIMILAR_JD_PATHS[0])
    # Repeat the same JD text to reach the recommended count — fine for
    # this test since we're only checking the warning logic, not content.
    similar_texts = [similar_text] * config.RECOMMENDED_SIMILAR_JDS

    result = similar_jobs.analyse_similar_jobs(target_text, similar_texts)

    assert result.meets_recommended_count
    assert result.warning == ""


def test_unparseable_similar_jd_does_not_block_the_others():
    target_text = _read(TARGET_JD_PATH)
    similar_texts = [_read(p) for p in SIMILAR_JD_PATHS] + [""]  # empty = unparseable

    result = similar_jobs.analyse_similar_jobs(target_text, similar_texts)

    assert result.similar_jds_requested == 4
    assert result.similar_jds_parsed == 3  # the empty one doesn't count
    assert any(not jd.is_valid for jd in result.similar_jds)
