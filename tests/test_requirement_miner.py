"""
tests/test_requirement_miner.py

Tests for requirement_miner.py. Covers:
  - mining known phrases (SQL, Excel, Power BI, etc.) out of the sample
    target job description
  - a requirement mentioning two known phrases yielding two mined entries
  - category is carried over correctly from the source requirement
  - an invalid JobParseResult yields no mined requirements (no crash)
"""

import config
import job_parser
import requirement_miner
from config import RequirementCategory


TARGET_JD_PATH = config.SAMPLE_DATA_DIR / "sample_jd_target_nhs_data_analyst.txt"


def test_mines_known_phrases_from_sample_jd():
    text = TARGET_JD_PATH.read_text(encoding="utf-8")
    parsed = job_parser.parse_job_description(text)

    mined = requirement_miner.mine_requirements(parsed)
    phrases = {m.canonical_phrase for m in mined}

    assert "SQL" in phrases
    assert "Excel" in phrases
    assert "Power BI" in phrases
    assert "Healthcare/NHS data experience" in phrases
    assert "Python" in phrases


def test_mined_requirement_keeps_correct_category():
    text = TARGET_JD_PATH.read_text(encoding="utf-8")
    parsed = job_parser.parse_job_description(text)
    mined = requirement_miner.mine_requirements(parsed)

    sql_matches = [m for m in mined if m.canonical_phrase == "SQL"]
    assert sql_matches
    assert sql_matches[0].category == RequirementCategory.REQUIRED

    python_matches = [m for m in mined if m.canonical_phrase == "Python"]
    assert python_matches
    assert python_matches[0].category == RequirementCategory.PREFERRED


def test_mined_requirement_traces_back_to_source_text():
    text = TARGET_JD_PATH.read_text(encoding="utf-8")
    parsed = job_parser.parse_job_description(text)
    mined = requirement_miner.mine_requirements(parsed)

    for item in mined:
        assert item.source_text != ""


def test_invalid_job_result_yields_no_mined_requirements():
    invalid_result = job_parser.parse_job_description("")  # is_valid = False

    mined = requirement_miner.mine_requirements(invalid_result)

    assert mined == []


def test_expanded_vocabulary_matches_real_requirements():
    text = (
        "Essential Criteria\n"
        "- Experience with Tableau or Power BI\n"
        "- Strong project management skills\n"
        "- Familiarity with Agile / Scrum methodologies\n"
        "- Knowledge of GDPR and data protection requirements\n"
        "- Experience with AWS\n"
    )
    parsed = job_parser.parse_job_description(text)
    mined = requirement_miner.mine_requirements(parsed)
    phrases = {m.canonical_phrase for m in mined}

    assert "Tableau" in phrases
    assert "Power BI" in phrases
    assert "Project management" in phrases
    assert "Agile" in phrases
    assert "GDPR" in phrases
    assert "AWS" in phrases


def test_short_ambiguous_terms_do_not_false_positive_on_ordinary_text():
    """
    Regression test for the exact bug class found earlier with the
    single-letter phrase 'R' matching almost any text containing the
    letter r. The new vocabulary deliberately avoids bare common English
    words (e.g. 'Go', 'Lead') as canonical phrases/surface forms — this
    test proves ordinary sentences using those everyday words don't
    trigger false matches for the technical terms they resemble.
    """
    text = (
        "Essential Criteria\n"
        "- Willingness to go the extra mile for our patients\n"
        "- Able to lead by example and support colleagues\n"
        "- Educated to degree level, grade C or above in Maths\n"
    )
    parsed = job_parser.parse_job_description(text)
    mined = requirement_miner.mine_requirements(parsed)
    phrases = {m.canonical_phrase for m in mined}

    # None of these everyday-word sentences should be mistaken for the
    # technical terms they superficially resemble.
    assert "Go programming" not in phrases
    assert "Leadership" not in phrases
    assert "C programming" not in phrases


def test_azure_and_java_require_disambiguating_context():
    # "azure" and "java" are also an ordinary colour word and a place/
    # coffee reference respectively — the vocabulary requires them to
    # appear with disambiguating context, not as a bare word.
    text = (
        "Desirable Criteria\n"
        "- The reception area has an azure blue colour scheme\n"
        "- Enjoys a good cup of java in the break room\n"
    )
    parsed = job_parser.parse_job_description(text)
    mined = requirement_miner.mine_requirements(parsed)
    phrases = {m.canonical_phrase for m in mined}

    assert "Microsoft Azure" not in phrases
    assert "Java programming" not in phrases


def test_early_years_vocabulary_matches_real_requirements():
    text = (
        "Essential Criteria\n"
        "- Sound knowledge of the EYFS and child development\n"
        "- Experience supporting children with special educational needs\n"
        "- Enhanced DBS check required\n"
        "- Confident with safeguarding and child protection procedures\n"
        "- Level 3 childcare qualification (or equivalent)\n"
        "\n"
        "Key Responsibilities\n"
        "- Acting as key worker for a small group of children\n"
        "- Building strong parental engagement\n"
        "- Liaising with the local authority and other agencies (multi-agency working)\n"
    )
    parsed = job_parser.parse_job_description(text)
    mined = requirement_miner.mine_requirements(parsed)
    phrases = {m.canonical_phrase for m in mined}

    assert "EYFS" in phrases
    assert "Child development" in phrases
    assert "Special educational needs (SEND)" in phrases
    assert "DBS check" in phrases
    assert "Safeguarding" in phrases
    assert "Child protection" in phrases
    assert "Level 3 childcare qualification" in phrases
    assert "Key worker (childcare)" in phrases
    assert "Parental engagement" in phrases
    assert "Local authority" in phrases
    assert "Multi-agency working" in phrases


def test_send_does_not_false_positive_on_the_verb_send():
    """
    Regression-style test for the exact bug class already found with
    'Java': the UK SEND acronym (Special Educational Needs and
    Disabilities) shares its lowercase form with the extremely common
    verb 'send'. Ordinary sentences using 'send' as a verb must not be
    mistaken for a SEND-related requirement.
    """
    text = (
        "Essential Criteria\n"
        "- Please send your completed application form by Friday\n"
        "- We will send further details after shortlisting\n"
    )
    parsed = job_parser.parse_job_description(text)
    mined = requirement_miner.mine_requirements(parsed)
    phrases = {m.canonical_phrase for m in mined}

    assert "Special educational needs (SEND)" not in phrases
