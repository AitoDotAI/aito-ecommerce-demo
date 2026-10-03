"""Churn drivers — which customer profiles churn more, via `_relate`.

Each driver answers "among customers who churned, how much more (or
less) common is this profile than among all customers?" That ratio is
`_relate`'s `lift`. The question is asked once per customer, on the
`customers` table, not once per customer-month: a customer who stayed
two years shouldn't weigh 24 times as much as one who left after a
month.

Profile fields are related by name (`"relate": "segment"`), which
returns one hit per value, each with its lift and the counts behind it.

Tenure is a number and is shown as three bands, which `_relate` can't
do on API v2:

  * a range as `relate` (`{"tenure_months": {"$gte": 18}}`) is refused
    with a 400 ("…is a combinator");
  * relating the field returns one hit per month count and leaves out
    the counts no churner has, so summing hits into bands undercounts
    the band (under 6 months came out 0.44×; the true lift is 0.23×).

So each band's lift is computed from four `_search limit=0` counts
(band, band among churners, everyone, churners), the same ratio
`_relate` reports for a field value.

Each row reads as "62 % of the 635 customers with this profile churned,
against 36 % of all customers". That is the lift's ratio, P(churn |
profile) / P(churn), equal to `_relate`'s P(profile | churn) /
P(profile).

Fields whose every value stays near lift 1 are reported by name as
"checked, no effect" rather than dropped silently. See ADR 0013
§"Amendment 2026-10-03".
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value


CHURNED = {"churned": True}

# Every discrete profile column on `customers`. Order count and spend
# are left out on purpose: churners stop ordering, so a low count is
# partly the outcome, not a cause.
PROFILE_FIELDS: list[str] = [
    "segment", "region", "pet_size",
    "lifestyle", "health_focus", "treat_affinity", "brand_loyalty",
]

# (label, `_search` filter) per tenure band.
TENURE_BANDS: list[tuple[str, dict]] = [
    ("under 6 months",    {"tenure_months": {"$lt": 6}}),
    ("6–17 months",       {"$and": [{"tenure_months": {"$gte": 6}},
                                    {"tenure_months": {"$lt": 18}}]}),
    ("18 months or more", {"tenure_months": {"$gte": 18}}),
]

# A lift within this distance of 1 is "no effect" for the list.
NEUTRAL_LIFT_BAND = 0.15
MAX_DRIVERS = 10


@dataclass(frozen=True)
class DriverRow:
    field: str                 # "segment", "region", "tenure", ...
    value: str                 # "aquarium_owner", "18 months or more", ...
    lift: float                # churn_rate / churn_rate_overall
    customers: int             # customers with this profile
    churners: int              # of whom churned
    churn_rate: float          # churners / customers
    churn_rate_overall: float  # churners / customers, everyone


@dataclass(frozen=True)
class ChurnDrivers:
    drivers: list[DriverRow]
    # Profile fields that were related but showed no value outside the
    # neutral band, e.g. ["lifestyle", "health_focus"].
    fields_without_effect: list[str]


def _row(field: str, value: str, hit: dict) -> DriverRow:
    # With `where: churned`, a hit's `fs` counts the value among churners
    # (`fOnCondition`) and among everyone (`f`); `fCondition` is all
    # churners and `n` all customers.
    fs = hit["fs"]
    return DriverRow(
        field=field,
        value=value,
        lift=round(float(hit["lift"]), 2),
        customers=int(fs["f"]),
        churners=int(fs["fOnCondition"]),
        churn_rate=round(fs["fOnCondition"] / fs["f"], 4),
        churn_rate_overall=round(fs["fCondition"] / fs["n"], 4),
    )


def _field_rows(client: AitoClient, field: str) -> list[DriverRow]:
    res = client.relate(table="customers", where=CHURNED, relate_field=field, limit=20)
    hits = res["hits"]
    if not hits:
        raise AitoError(f"_relate customers churned → {field} returned no hits")
    return [_row(field, str(related_value(hit, field)), hit) for hit in hits]


def _count(client: AitoClient, where: dict | None) -> int:
    return client.search("customers", where=where, limit=0)["total"]


def _tenure_row(client: AitoClient, label: str, band: dict, customers: int, churners: int) -> DriverRow:
    in_band = _count(client, band)
    churners_in_band = _count(client, {"$and": [CHURNED, band]})
    if in_band == 0:
        raise AitoError(f"no customers with tenure {label} ({band}): check the band bounds")
    churn_rate = churners_in_band / in_band
    churn_rate_overall = churners / customers
    return DriverRow(
        field="tenure",
        value=label,
        lift=round(churn_rate / churn_rate_overall, 2),
        customers=in_band,
        churners=churners_in_band,
        churn_rate=round(churn_rate, 4),
        churn_rate_overall=round(churn_rate_overall, 4),
    )


def is_driver(row: DriverRow) -> bool:
    return abs(row.lift - 1.0) >= NEUTRAL_LIFT_BAND


def get_churn_drivers(client: AitoClient) -> ChurnDrivers:
    """Relate churn to every profile field, and count it per tenure band, in parallel."""
    customers = _count(client, None)
    churners = _count(client, CHURNED)
    with ThreadPoolExecutor(max_workers=len(PROFILE_FIELDS) + len(TENURE_BANDS)) as pool:
        field_jobs = {f: pool.submit(_field_rows, client, f) for f in PROFILE_FIELDS}
        tenure_jobs = [pool.submit(_tenure_row, client, label, band, customers, churners)
                       for label, band in TENURE_BANDS]
        rows_by_field = {"tenure": [job.result() for job in tenure_jobs]}
        rows_by_field.update({f: job.result() for f, job in field_jobs.items()})

    drivers = [row for rows in rows_by_field.values() for row in rows if is_driver(row)]
    drivers.sort(key=lambda r: abs(r.lift - 1.0), reverse=True)
    without_effect = [f for f, rows in rows_by_field.items() if not any(is_driver(r) for r in rows)]
    return ChurnDrivers(drivers=drivers[:MAX_DRIVERS], fields_without_effect=without_effect)
