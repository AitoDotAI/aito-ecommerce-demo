"""The shopkeeper agent's gate (ADR 0052): act, suggest, stay quiet, or ask a person.

Every proposed action is judged on three things, each a number the step already shows: the lift (how many
points more likely the customer is to order after the action than after none), how many past rows match
the customer's exact situation and the action, and the kind of action. The lift is Aito's estimate over the
whole action table; the matching rows are a check that this situation has history, not what the lift rests on. The store sets the thresholds; the defaults below are what
the app recommends. The judgement is a pure function, so the page can re-judge a stored run when the
shopkeeper moves a threshold, and a test can state each rule.
"""

from __future__ import annotations

from dataclasses import dataclass

ACT, SUGGEST, QUIET, NEVER_AUTO = "act", "suggest", "quiet", "never_auto"
OUTCOMES = (ACT, SUGGEST, QUIET, NEVER_AUTO)

# Kinds whose cost is paid on every order, including the ones that would have come anyway (ADR 0051):
# the agent proposes them, a person sends them.
RECOMMENDED_NEVER_AUTO = frozenset({"discount", "voucher", "apology"})


@dataclass(frozen=True)
class GateSettings:
    act_lift: float = 0.15          # at or above: the agent acts, if the kind allows it
    suggest_lift: float = 0.05      # at or above, and below act_lift: queued for a person
    min_rows: int = 10              # past rows matching this action in this exact context; fewer is thin
    never_auto: frozenset[str] = RECOMMENDED_NEVER_AUTO

    def __post_init__(self):
        if not 0 <= self.suggest_lift <= self.act_lift <= 1:
            raise ValueError(f"Thresholds must satisfy 0 <= suggest_lift <= act_lift <= 1, got {self.suggest_lift} and {self.act_lift}")
        if self.min_rows < 0:
            raise ValueError(f"min_rows must not be negative, got {self.min_rows}")


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str                     # one sentence the step shows next to the outcome


def decide(action: str, label: str, lift: float, net_eur: float, rows: int, settings: GateSettings) -> Decision:
    """Judge one proposed action. The rules run in this order; the first that applies wins."""
    if action == "none":
        return Decision(QUIET, "No candidate beats doing nothing.")
    if net_eur <= 0:
        return Decision(QUIET, f"{label} adds {net_eur:.2f} € over no action after its cost.")
    if rows < settings.min_rows:
        return Decision(QUIET, f"Only {rows} past rows match this customer's exact situation and {label.lower()}; the rule asks for {settings.min_rows}.")
    if action in settings.never_auto:
        return Decision(NEVER_AUTO, f"{label} is a kind the store always sends through a person.")
    if lift >= settings.act_lift:
        return Decision(ACT, f"A lift of {lift * 100:.0f} points reaches the {settings.act_lift * 100:.0f}-point bar; {rows} past rows match this exact situation.")
    if lift >= settings.suggest_lift:
        return Decision(SUGGEST, f"A lift of {lift * 100:.0f} points is below the {settings.act_lift * 100:.0f}-point bar to act.")
    return Decision(QUIET, f"A lift of {lift * 100:.0f} points is below the {settings.suggest_lift * 100:.0f}-point bar to propose.")
