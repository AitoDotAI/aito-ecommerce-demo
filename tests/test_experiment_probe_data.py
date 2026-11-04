"""The synthetic shop of the experiments probe: its true chances, and what a plain A/B test and an oracle would earn."""
import random

from scripts.experiment_probe_data import ARMS, LIFT, OFFER_SHARE, Product, Shopper, chance, leans, oracle_numbers, profit

SHOPPER = Shopper("S0001", {"discount": "high", "health_focus": "low", "visual": "high"}, ("treats", "toys"))
OFFER = Product("P001", "treats", "offer", 20.0, 12.0, 0.05)


def test_an_offer_raises_the_chance_by_the_shoppers_sensitivity_and_the_control_arm_does_not():
    control, offer = chance(SHOPPER, OFFER, "list"), chance(SHOPPER, OFFER, "offer")
    assert offer == control * LIFT["offer"]["high"]


def test_an_offer_costs_margin_so_the_same_lift_pays_for_a_sensitive_shopper_and_not_for_an_insensitive_one():
    insensitive = Shopper("S0002", {"discount": "low", "health_focus": "low", "visual": "low"}, ("treats", "toys"))
    assert OFFER.margin("offer") == round(20.0 * OFFER_SHARE - 12.0, 2)
    assert profit(SHOPPER, OFFER, "offer") > profit(SHOPPER, OFFER, "list")
    assert profit(insensitive, OFFER, "offer") < profit(insensitive, OFFER, "list")


def test_a_title_or_image_arm_has_the_same_margin_as_the_control():
    title = Product("P002", "toys", "title", 10.0, 6.0, 0.05)
    assert title.margin("plain") == title.margin("benefit")


def test_a_shoppers_lean_is_one_of_three_bands_for_each_kind_they_were_shown():
    rng = random.Random(1)
    products = {"P001": OFFER}
    train = [{"shopper": f"S{i % 30}", "sku": "P001", "arm": rng.choice(ARMS["offer"]), "purchased": rng.random() < 0.2} for i in range(900)]
    bands = leans(train, products)
    assert set(bands.values()) <= {"lo", "mid", "hi"} and {k for _, k in bands} == {"offer"} and len(bands) == 30


def test_an_oracle_beats_a_plain_winner_which_beats_the_control_in_the_seeded_world():
    profit_per_showing = oracle_numbers(7)["profit_per_showing"]
    assert profit_per_showing["P3 oracle"] > profit_per_showing["P1 winner"] > profit_per_showing["P0 control"]
