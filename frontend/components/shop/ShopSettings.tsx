"use client";

/** How "Picked for you" is personalised: two choices behind a ⚙ next to its title. The defaults are the
 *  shop's own history without a pets filter, starting from the last order. Both are experiments the held-out
 *  sweeps did not favour (ADR 0033, last-basket-prereg.md), so the measurement is stated beside them. */
export type LastOrder = "" | "cart" | "path" | "path2";
export type StateRank = "" | "offer" | "change";
export type Personalisation = "history" | "history-pets" | "pets";

export default function ShopSettings({ personalisation, lastOrder, season, month, months, stateRank, onPersonalisation, onLastOrder, onSeason, onMonth, onStateRank }: {
  personalisation: Personalisation;
  lastOrder: LastOrder;
  season: boolean;
  month: string;
  months: Array<{ value: string; label: string }>;
  stateRank: StateRank;
  onPersonalisation: (value: Personalisation) => void;
  onLastOrder: (mode: LastOrder) => void;
  onSeason: (on: boolean) => void;
  onMonth: (month: string) => void;
  onStateRank: (mode: StateRank) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontWeight: 600 }}>Personalise by</span>
        <select aria-label="Personalisation" className="search-input" style={{ paddingLeft: 10 }} value={personalisation}
                onChange={(e) => onPersonalisation(e.target.value as Personalisation)}>
          <option value="history">Their own history, no pets filter</option>
          <option value="history-pets">Their own history, pets filter kept</option>
          <option value="pets">Their pets only</option>
        </select>
      </label>
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontWeight: 600 }}>Start from their last order</span>
        <select aria-label="Last order" className="search-input" style={{ paddingLeft: 10 }} value={lastOrder}
                onChange={(e) => onLastOrder(e.target.value as LastOrder)}>
          <option value="cart">Its items, as if they were in the cart</option>
          <option value="path">By link: its words on the order (chained baskets)</option>
          <option value="path2">By link: the last two orders</option>
          <option value="">Not used</option>
        </select>
      </label>
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontWeight: 600 }}>Product state in the ranking</span>
        <select aria-label="Product state" className="search-input" style={{ paddingLeft: 10 }} value={stateRank}
                onChange={(e) => onStateRank(e.target.value as StateRank)}>
          <option value="">Not used: Aito&apos;s order only</option>
          <option value="offer">Offers lift: score × the offer band&apos;s lift</option>
          <option value="change">Changes lift: what is new since last month (offer, stars)</option>
        </select>
      </label>
      <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <input type="checkbox" checked={season} onChange={(e) => onSeason(e.target.checked)} />
        <span><strong>Use the season</strong>: the month counts as evidence ("Sells in April ×2.0")</span>
      </label>
      {season && (
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontWeight: 600 }}>Month</span>
          <select aria-label="Month" className="search-input" style={{ paddingLeft: 10, flex: 1 }} value={month}
                  onChange={(e) => onMonth(e.target.value)}>
            {months.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </label>
      )}
      <div className="card-sub" style={{ lineHeight: 1.5 }}>
        Product state is an experiment: the score is Aito&apos;s probability times the shop-wide lifts Aito learned for the
        month&apos;s offer band and stars, a multiplication this app does, not one Aito query. Whether it ranks better is
        pre-registered in <code>state-rank-prereg.md</code> and has not been run.
        <br /><br />
        Season is off by default: it is the same shop-wide lift for every product, and it lifted other pets&apos;
        products over a dog household&apos;s own. What the held-out sweeps measured, on release 2 data in October 2026 and not re-run on release 3b: ranking by the customer&apos;s own history ties on ranking and overconfides the
        percentages on average (ADR 0033); a long history personalises well and a thin one (Anna has two orders) does
        not. The last order as cart words lost on both hit@12 and Brier (<code>last-basket-prereg.md</code>). They are
        the demo&apos;s defaults because they show the personalisation; &quot;Their pets only&quot; is what measured best.
      </div>
    </div>
  );
}
