"""The reviews and NPS tables carry the theme tags of each message as a column Aito can mine patterns over."""
from src.data_loader import load_fixture
from src.feedback_themes import themes_of
from src.schema import SCHEMAS


def test_both_feedback_tables_declare_a_nullable_themes_column_of_space_separated_tags():
    for table in ("reviews", "nps_responses"):
        column = SCHEMAS[table]["columns"]["themes"]

        assert column["type"] == "Text" and column["nullable"] is True and column["analyzer"] == "whitespace", table


def test_a_loaded_review_carries_the_tags_of_its_text():
    review = next(r for r in load_fixture("reviews") if "box was damaged" in r["text"])

    assert review["themes"] == "late-delivery damaged-packaging"


def test_a_loaded_nps_answer_carries_the_tags_of_its_comment_and_none_when_it_has_no_comment():
    answers = load_fixture("nps_responses")
    with_comment = next(a for a in answers if a.get("comment"))
    without = next(a for a in answers if not a.get("comment"))

    assert with_comment["themes"] == " ".join(themes_of(with_comment["comment"]))
    assert "themes" not in without
