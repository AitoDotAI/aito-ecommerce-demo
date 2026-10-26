import ProductImage from "@/components/shop/ProductImage";
import { fmtEur } from "@/lib/api";
import type { ProductView } from "@/lib/types";
import { BAND_LABEL, monthLabel, words } from "./labels";

/** The product at the top of the Product view: its picture, what it is, and its state this month as a
 *  row of facts, so the numbers below read as being about something. Read-only. */
export default function ProductHero({ view }: { view: ProductView }) {
  const { product: p, state: s, decision } = view;
  const onOffer = decision.current_band !== "none";
  const stars = s.rating_band === "unrated" ? null : s.rating_band;
  const flags = [
    s.age === "new" ? "New" : null,
    s.rival_launched ? "A rival launched recently" : null,
    s.price_change === "rise" ? "After a price rise" : null,
  ].filter((f): f is string => f !== null);

  return (
    <div className="card product-hero">
      <ProductImage petType={p.pet_type} category={p.category} size="page" />
      <div className="product-hero-main">
        <div className="product-hero-crumb">{words(p.pet_type)} · {words(p.category)} · {p.brand}</div>
        <h2 className="product-hero-name">{p.name}</h2>
        <div className="product-hero-chips">
          {onOffer && <span className="pill pill-red">{BAND_LABEL[decision.current_band]}</span>}
          {flags.map((f) => <span key={f} className="pill pill-blue">{f}</span>)}
        </div>
      </div>
      <dl className="product-hero-facts">
        <div><dt>List price</dt><dd>{fmtEur(p.price_eur, 2)}</dd></div>
        <div><dt>Cost</dt><dd>{fmtEur(p.unit_cost_eur, 2)}</dd></div>
        <div><dt>Stars</dt><dd>{stars ? `${stars} ★` : "none yet"}<small>{s.reviews} review{s.reviews === 1 ? "" : "s"}</small></dd></div>
        <div><dt>Sold in {monthLabel(view.month)}</dt><dd>{s.units_sold}<small>units</small></dd></div>
      </dl>
    </div>
  );
}
