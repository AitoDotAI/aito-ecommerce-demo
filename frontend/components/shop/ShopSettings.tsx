"use client";

/** How "Picked for you" is personalised: two choices behind a ⚙ next to its title. The defaults are the
 *  shop's own history without a pets filter, starting from the last order. Both are experiments the held-out
 *  sweeps did not favour (ADR 0033, last-basket-prereg.md), so the measurement is stated beside them. */
export type Personalisation = "history" | "history-pets" | "pets";

export default function ShopSettings({ personalisation, lastOrder, onPersonalisation, onLastOrder }: {
  personalisation: Personalisation;
  lastOrder: boolean;
  onPersonalisation: (value: Personalisation) => void;
  onLastOrder: (on: boolean) => void;
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
      <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <input type="checkbox" checked={lastOrder} onChange={(e) => onLastOrder(e.target.checked)} />
        <span><strong>Start from their last order</strong>: its items count as if they were in the cart</span>
      </label>
      <div className="card-sub" style={{ lineHeight: 1.5 }}>
        What the held-out sweeps measured: ranking by the customer&apos;s own history ties on ranking and overconfides the
        percentages on average (ADR 0033); a long history personalises well and a thin one (Anna has two orders) does
        not. The last order as cart words lost on both hit@12 and Brier (<code>last-basket-prereg.md</code>). They are
        the demo&apos;s defaults because they show the personalisation; &quot;Their pets only&quot; is what measured best.
      </div>
    </div>
  );
}
