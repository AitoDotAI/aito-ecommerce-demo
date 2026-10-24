"""The Markdown report of one backtest run (ADR 0036).

The header (dataset, cutoff, counts, dropped rows) comes first, then the
hit@1 table by slice with intervals and the verdict of each slice, the
sentences `src/backtest_wording.py` allows, recall@10 beside its ceiling,
and ten example buyers. A merchant's result is theirs; the report says so.
"""

from __future__ import annotations

from src.backtest_aito import aito_env_for
from src.backtest_metrics import AITO, BASELINE_ORDER, K, SliceResult
from src.backtest_run import BacktestRun
from src.backtest_wording import interval_text, signed_interval, slice_label, slice_sentence, verdict

SHOWN_ORDERED_CODES = 8


def render_report(run: BacktestRun) -> str:
    methods = ([AITO] if run.aito_ran else []) + list(BASELINE_ORDER)
    sections = [_header(run), _hit1_table(run.slices, methods),
                "## What it says\n\n" + "\n".join(f"- {slice_sentence(s)}" for s in run.slices),
                _recall_table(run.slices, methods), _examples(run), _method_notes()]
    return "\n\n".join(sections) + "\n"


def _header(run: BacktestRun) -> str:
    dataset = run.dataset
    sizes = {s.name: s.buyers for s in run.slices}
    customers = {order.customer_id for order in dataset.train}
    codes = {code for order in dataset.train for code in order.codes}
    dropped = ", ".join(f"{reason} {count:,}" for reason, count in dataset.dropped_rows.items()) or (
        "none at this step" + (" (ADR 0034's cleaning ran in `./do uci-prepare`)" if dataset.name == "uci" else ""))
    notes = ", ".join(f"{note} {count:,}" for note, count in dataset.notes.items()) or "none"
    aito = (f"env `{aito_env_for(dataset.name)}`, ADR 0034's `_predict`" if run.aito_ran
            else "not run (offline): the three baselines only")
    return "\n".join([
        f"# Reorder backtest: {dataset.name}",
        "",
        f"- **Dataset:** {dataset.source}",
        f"- **Cutoff:** {dataset.cutoff}. Train = orders before it; test = each buyer's first order on or after it.",
        f"- **Training:** {len(dataset.train):,} orders, {len(customers):,} buyers, {len(codes):,} codes",
        f"- **Scored buyers:** {len(dataset.test_orders):,} "
        f"({', '.join(f'{slice_label(name)}: {n:,}' for name, n in sizes.items())})",
        f"- **Dropped rows:** {dropped}",
        f"- **Counted, kept:** {notes}",
        f"- **Aito:** {aito}",
        "",
        "This result is this dataset's own, with its own uncertainty. It is not a claim about any other shop.",
    ])


def _hit1_table(slices: list[SliceResult], methods: list[str]) -> str:
    head = ["Slice", "Buyers"] + methods + ["Best baseline", "Aito − best", "Verdict"]
    rows = []
    for s in slices:
        cells = [slice_label(s.name), f"{s.buyers:,}"]
        cells += [interval_text(s.hit1[m]) if s.buyers else "—" for m in methods]
        cells.append(s.best_baseline or "—")
        cells.append(signed_interval(s.aito_minus_best) if s.aito_minus_best else "—")
        cells.append(verdict(s).value)
        rows.append(cells)
    return ("## Hit@1 by slice (primary)\n\nThe share of buyers whose next order held the method's top code; "
            "95 % intervals in brackets.\n\n" + _table(head, rows))


def _recall_table(slices: list[SliceResult], methods: list[str]) -> str:
    head = ["Slice"] + methods + [f"Ceiling@{K}"]
    rows = [[slice_label(s.name)] + [f"{s.recall10[m]:.4f}" if s.buyers else "—" for m in methods]
            + [f"{s.recall10_ceiling:.4f}" if s.buyers else "—"] for s in slices]
    return (f"## Recall@{K} by slice (secondary)\n\nThe share of the next order's codes in the top {K}. "
            f"The ceiling is the most a {K}-slot list can reach given basket sizes.\n\n" + _table(head, rows))


def _examples(run: BacktestRun) -> str:
    title = "## Ten example buyers\n\n"
    if not run.aito_ran:
        return title + "Aito was not run, so there are no Aito suggestions to show."
    rows = []
    for e in run.examples:
        shown = ", ".join(e.ordered[:SHOWN_ORDERED_CODES])
        more = f" … ({len(e.ordered)} codes)" if len(e.ordered) > SHOWN_ORDERED_CODES else ""
        rows.append([e.customer_id, str(e.prior_orders), e.top_code, "yes" if e.hit else "no",
                     e.why, shown + more])
    return (title + "Picked by a hash of the buyer id, before any result.\n\n"
            + _table(["Buyer", "Prior orders", "Aito's top", "In next order", "Aito's $why", "What they ordered"],
                     rows))


def _method_notes() -> str:
    return "\n".join([
        "## How to read this",
        "",
        "- Intervals: mean ± 1.96 · SE over buyers; Aito − best is paired buyer by buyer.",
        "- Best baseline: the strongest of the three in that slice, by its hit@1 point estimate; "
        "on a tie the simpler one (popularity, then personal repeat, then EASE).",
        "- A tie means the interval for Aito − best spans 0. Only a slice whose interval excludes 0 is read "
        "as a difference; a slice under 30 buyers is too few to read.",
        "- Baselines: Aito core's benchmark code (aito-core 625867faca), EASE λ = 250, "
        "personal repeat half-life 6 months.",
    ])


def _table(head: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows]
    return "\n".join(lines)
