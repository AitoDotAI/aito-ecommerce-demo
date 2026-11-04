"""The Feedback tab's pattern lists, counted over the reviews and NPS answers of the chosen customers only."""
import pytest

from src.feedback_segment_patterns import segment_patterns

PRODUCTS = {
    "SKU-A": {"sku": "SKU-A", "name": "Acme Dog Food Large", "brand": "Acme", "category": "dry-food", "pet_type": "dog"},
    "SKU-B": {"sku": "SKU-B", "name": "Acme Cat Food Large", "brand": "Acme", "category": "dry-food", "pet_type": "cat"},
    "SKU-C": {"sku": "SKU-C", "name": "Acme Dog Toy Large", "brand": "Acme", "category": "toys", "pet_type": "dog"},
}
DAMAGED = "Packaging of the Whiskas Indoor Tuna Sticks Treats 500g was crushed when it came."
PRAISE = "The Felix Senior Tuna Cat Food 150g is just what we needed."


def review(customer, sku, rating, text):
    return {"customer_id": customer, "product_sku": sku, "rating": rating, "text": text}


def answer(customer, sku, group, comment=None):
    return {"customer": customer, "product_state": f"{sku}-2025-03", "nps_group": group, "comment": comment}


REVIEWS = ([review(f"N{i}", "SKU-A", 1, DAMAGED) for i in range(4)] + [review(f"N{i}", "SKU-B", 5, PRAISE) for i in range(6)]
           + [review(f"S{i}", "SKU-B", 1, DAMAGED) for i in range(3)] + [review(f"S{i}", "SKU-A", 5, PRAISE) for i in range(3)])
ANSWERS = [answer("N0", "SKU-A", "detractor", DAMAGED), answer("N1", "SKU-A", "promoter", PRAISE), answer("S0", "SKU-B", "detractor")]


def sections(customers, group="stars", **products):
    return segment_patterns(REVIEWS, ANSWERS, customers, PRODUCTS)[group]["sections"]


def test_the_rows_counted_are_those_of_the_chosen_customers_not_everyones():
    north = {f"N{i}" for i in range(6)}
    stars = segment_patterns(REVIEWS, ANSWERS, north, PRODUCTS)["stars"]
    assert (stars["rows"], stars["of"]) == (4, 10)   # 1–2 star reviews, all reviews, of customers N0..N5


def test_a_theme_row_counts_the_poor_reviews_with_the_theme_and_all_the_reviews_with_it_in_the_segment():
    theme = next(r for r in sections({f"N{i}" for i in range(6)})["themes"] if r["label"] == "damaged-packaging")
    assert (theme["k"], theme["overall"]) == (4, 4)
    assert theme["clauses"] == [{"field": "themes", "word": "damaged-packaging"}]


def test_a_segment_with_other_customers_gives_other_counts():
    south = {"S0", "S1", "S2"}
    theme = next(r for r in sections(south)["themes"] if r["label"] == "damaged-packaging")
    assert (theme["k"], theme["overall"]) == (3, 3)


def test_a_product_row_is_named_and_filters_by_its_sku():
    product = next(r for r in sections({f"N{i}" for i in range(6)})["products"] if r["label"] == "Acme Dog Food Large")
    assert (product["k"], product["overall"]) == (4, 4)
    assert product["clauses"] == [{"field": "product_sku", "value": "SKU-A"}]


def test_a_product_and_theme_row_needs_two_poor_rows_and_names_both():
    rows = sections({f"N{i}" for i in range(6)})["products and themes"]
    assert [r["label"] for r in rows] == ["Acme Dog Food Large AND damaged-packaging"]
    assert rows[0]["clauses"] == [{"field": "product_sku", "value": "SKU-A"}, {"field": "themes", "word": "damaged-packaging"}]
    assert rows[0]["k"] == 4


def test_detractors_use_the_product_of_the_order_and_the_comment_themes():
    rows = sections({"N0", "N1", "S0"}, "detractors")["themes"]
    theme = next(r for r in rows if r["label"] == "damaged-packaging")
    assert (theme["k"], theme["overall"]) == (1, 1)
    assert theme["clauses"] == [{"field": "themes", "word": "damaged-packaging"}]
    product = next(r for r in sections({"N0", "N1", "S0"}, "detractors")["products"] if r["label"] == "Acme Dog Food Large")
    assert product["clauses"] == [{"field": "product_state.product_sku", "value": "SKU-A"}]


def test_a_product_line_is_a_brand_with_a_word_of_the_name_shared_by_three_products():
    lines = {r["label"]: r for r in sections({f"N{i}" for i in range(6)})["brand and product-name word"]}
    assert set(lines) == {"Acme · Large"}   # "Dog" and "Food" are in two products only
    assert (lines["Acme · Large"]["k"], lines["Acme · Large"]["overall"]) == (4, 10)
    assert lines["Acme · Large"]["clauses"] == [{"field": "product_sku.brand", "value": "Acme"}, {"field": "product_sku.name", "word": "Large"}]


def test_rows_are_ordered_by_the_chance_of_luck_smallest_first():
    chances = [r["p"] for r in sections({f"N{i}" for i in range(6)})["themes"]]
    assert chances == sorted(chances)


def test_no_customers_gives_empty_lists():
    assert all(rows == [] for rows in sections(set()).values())


MINED = {"stars": {"sections": {"mined by Aito ($patterns)": [
    {"label": "category=shipping AND product=Acme Dog Food Large", "k": 99, "overall": 99, "p": 0.5, "lift": 1.0, "aito": {"lift": 2.0}, "products": None,
     "clauses": [{"field": "product_sku", "value": "SKU-A"}, {"field": "themes", "word": "damaged-packaging"}]}]}},
    "detractors": {"sections": {"mined by Aito ($patterns)": []}}}


def test_a_mined_pattern_is_recounted_in_the_segment_with_new_counts_chance_and_lift():
    north = {f"N{i}" for i in range(6)}
    out = segment_patterns(REVIEWS, ANSWERS, north, PRODUCTS, MINED)["stars"]["sections"]["mined by Aito ($patterns)"]
    assert len(out) == 1 and out[0]["label"] == "category=shipping AND product=Acme Dog Food Large"
    assert (out[0]["k"], out[0]["overall"]) == (4, 4)
    assert out[0]["p"] < 0.5 and out[0]["aito"] is None


def test_a_mined_pattern_the_segment_has_no_rows_for_is_kept_with_zero_rows():
    south = {"S0", "S1", "S2"}
    out = segment_patterns(REVIEWS, ANSWERS, south, PRODUCTS, MINED)["stars"]["sections"]["mined by Aito ($patterns)"]
    assert (out[0]["k"], out[0]["overall"], out[0]["p"], out[0]["lift"]) == (0, 0, 1.0, None)
