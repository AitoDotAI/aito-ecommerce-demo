"use client";

import { Suspense, useEffect, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { shopPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import FinePrint from "@/components/shell/FinePrint";
import NotFoundNotice from "@/components/shell/NotFoundNotice";
import CartPanel from "@/components/shop/CartPanel";
import ProductCard from "@/components/shop/ProductCard";
import ProductDrawer from "@/components/shop/ProductDrawer";
import SuggestionsPanel from "@/components/shop/SuggestionsPanel";
import { useSetUrlParams, useUrlState } from "@/lib/use-url-state";
import { SANDBOX_MONTH, SANDBOX_PARAM } from "@/lib/sandbox";
import type { ShopGrid, ShopSearch, ShopShopper, ShopSuggestions } from "@/lib/types";

// The data's window: May 2024 to April 2026 (the latest month).
const MONTHS = Array.from({ length: 24 }, (_, i) => {
  const d = new Date(2026, 3 - i, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
});
const monthLabel = (m: string) =>
  new Date(Number(m.slice(0, 4)), Number(m.slice(5)) - 1, 1).toLocaleString("en", { month: "long", year: "numeric" });

/**
 * Shop (ADR 0031): be a shopper, fill a cart, and watch Aito re-rank.
 * Backend: src/shop_grid.py, src/shop_search.py, src/shop_product.py, src/shop_suggestions.py.
 */
function ShopView() {
  usePagePanel(shopPanel(), {
    title: "Shop",
    description: "Be a shopper: the cart, the month and their history change what Aito suggests.",
    breadcrumb: "Shop",
  });
  const { setPanel } = useShell();
  const [shopperKey, setShopperKey] = useUrlState("shopper", "paivi");
  // In a sandbox (ADR 0043) the Shop opens on May 2026: the month the levers write.
  const [sandbox] = useUrlState(SANDBOX_PARAM, "");
  const [month, setMonth] = useUrlState("month", sandbox ? SANDBOX_MONTH : "2026-04");
  const months = sandbox ? [SANDBOX_MONTH, ...MONTHS] : MONTHS;
  const [cartParam] = useUrlState("cart", "");
  // An experiment: also rank by the customer themselves (`context.customer`, ADR 0033), not only their pets.
  const [identityParam] = useUrlState("identity", "");
  const [trustParam] = useUrlState("trust", "");
  const identity = identityParam === "1" ? `&identity=1${trustParam === "1" ? "&trust=1" : ""}` : "";
  const [openSku] = useUrlState("product", "");
  const [query] = useUrlState("q", "");
  const [typed, setTyped] = useState(query);
  const setUrl = useSetUrlParams();
  const cart = cartParam ? cartParam.split(",") : [];
  const setCart = (skus: string[]) => setUrl({ cart: skus.length ? skus.join(",") : null });
  const addToCart = (skus: string[]) => setCart([...cart, ...skus.filter((s) => !cart.includes(s))]);

  const [shoppers, setShoppers] = useState<ShopShopper[]>([]);
  const [grid, setGrid] = useState<ShopGrid | null>(null);
  const [suggestions, setSuggestions] = useState<ShopSuggestions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState<string | null>(null);
  const [suggestionsError, setSuggestionsError] = useState<string | null>(null);
  const [search, setSearch] = useState<ShopSearch | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<{ shoppers: ShopShopper[] }>("/api/shop/shoppers").then((r) => setShoppers(r.shoppers), (e) => setError(String(e)));
  }, []);

  useEffect(() => {
    let current = true;
    setError(null);
    setNotFound(null);
    apiFetch<ShopGrid>(`/api/shop/grid?shopper=${shopperKey}&month=${month}&cart=${encodeURIComponent(cartParam)}${identity}`)
      .then((g) => {
        if (!current) return;
        setGrid(g);
        if (!query) setPanel({ ...shopPanel(), query: highlightQuery(g.last_query.body) });
      }, (e) => {
        if (!current) return;
        if (e instanceof ApiError && e.status === 404) setNotFound(e.serverMessage ?? e.message);
        else setError(String(e));
      });
    return () => { current = false; };
  }, [shopperKey, month, cartParam, identity, query, setPanel]);

  useEffect(() => {
    // A search is ranked as the grid is: same shopper, month, cart and rule.
    let current = true;
    setTyped(query);
    setSearchError(null);
    if (!query) { setSearch(null); return; }
    apiFetch<ShopSearch>(`/api/shop/search?q=${encodeURIComponent(query)}&shopper=${shopperKey}&month=${month}` +
                         `&cart=${encodeURIComponent(cartParam)}${identity}`)
      .then((r) => {
        if (!current) return;
        setSearch(r);
        setPanel({ ...shopPanel(), query: highlightQuery(r.last_query.body) });
      }, (e) => { if (current) setSearchError(String(e)); });
    return () => { current = false; };
  }, [query, shopperKey, month, cartParam, identity, setPanel]);

  useEffect(() => {
    // As of the picked month and the cart, like the grid: later orders haven't
    // happened yet, and a kit item in the cart counts as owned.
    let current = true;
    setSuggestions(null);
    setSuggestionsError(null);
    apiFetch<ShopSuggestions>(`/api/shop/suggestions?shopper=${shopperKey}&month=${month}` +
                              `&cart=${encodeURIComponent(cartParam)}`)
      .then((s) => { if (current) setSuggestions(s); }, (e) => { if (current) setSuggestionsError(String(e)); });
    return () => { current = false; };
  }, [shopperKey, month, cartParam]);

  const shown = grid && grid.shopper.key === shopperKey ? grid : null;
  const stale = !!shown && (shown.month !== month || shown.cart.map((p) => p.sku).join(",") !== cartParam);
  const found = query && search?.query === query ? search : null;
  const shopperName = shoppers.find((s) => s.key === shopperKey)?.name ?? shopperKey;

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Shop</div>
        <div className="page-desc">
          Be one of these shoppers. What Aito suggests follows who they are, the month, what is in the
          cart, and what they bought last time.
        </div>
      </div>

      <div className="search-wrap" style={{ flexWrap: "wrap", gap: 8 }}>
        {shoppers.map((s) => (
          <button key={s.key} type="button" title={s.story}
                  className={`customer-chip${s.key === shopperKey ? " selected" : ""}`}
                  onClick={() => setUrl({ shopper: s.key, cart: null, product: null, q: null })}
                  style={{ border: "1px solid var(--border)" }}>
            <span aria-hidden="true">{s.emoji}</span>{s.name}
          </button>
        ))}
        <select aria-label="Month" className="search-input" style={{ width: "auto", paddingLeft: 12 }}
                value={month} onChange={(e) => setMonth(e.target.value)}>
          {months.map((m) => <option key={m} value={m}>{monthLabel(m)}{m === SANDBOX_MONTH ? " (sandbox)" : ""}</option>)}
        </select>
        <select aria-label="Personalisation" className="search-input" style={{ width: "auto", paddingLeft: 12 }}
                value={identityParam === "1" ? (trustParam === "1" ? "trust" : "own") : "pets"}
                onChange={(e) => setUrl({ identity: e.target.value === "pets" ? null : "1", trust: e.target.value === "trust" ? "1" : null })}>
          <option value="pets">Personalised by pets</option>
          <option value="own">By their own history (pets filter kept)</option>
          <option value="trust">By their own history, no pets filter</option>
        </select>
      </div>
      {identityParam === "1" && (
        <div className="card-sub" style={{ margin: "4px 0" }}>
          Experiment: ranked with the customer themselves in the query. The sweeps found this ties on ranking and
          overconfides the percentages on average (ADR 0033). A long history personalises well; a thin one
          (Anna has two orders) does not: with no pets filter she is shown dog treats.
        </div>
      )}
      {shown && (
        <div className="card-sub" style={{ margin: "4px 0 12px" }}>
          {shown.shopper.story}
          {shown.rule && <> Their declared diet, <strong>{shown.rule}</strong>, is applied as a filter: Aito ranks only food that keeps it.</>}
        </div>
      )}

      <form role="search" className="search-wrap" style={{ gap: 8 }}
            onSubmit={(ev) => { ev.preventDefault(); setUrl({ q: typed.trim() || null }); }}>
        <input className="search-input" type="search" aria-label="Search the shop" value={typed}
               style={{ paddingLeft: 12 }}
               placeholder="Search the shop, e.g. dental, hay, grain free"
               onChange={(ev) => setTyped(ev.target.value)} />
        <button className="btn" type="submit">Search</button>
        {query && <button className="btn btn-ghost" type="button" onClick={() => setUrl({ q: null })}>Clear</button>}
      </form>

      {notFound && (
        <NotFoundNotice message={notFound} resetLabel="Start over with the first shopper, with an empty cart"
                        onReset={() => setUrl({ shopper: null, cart: null, product: null })} />
      )}
      {error && <ErrorState title="Couldn't load the shop" message={error} />}

      {!error && !notFound && (
        <div className={`shop-layout${query ? " shop-searching" : ""}`}>
          {query ? (
            <div style={{ minWidth: 0 }}>
              <div className="card-sub" style={{ marginBottom: 8 }}>
                {searchError
                  ? <span style={{ color: "var(--red)" }}>Couldn&apos;t search: {searchError}</span>
                  : !found ? <>Searching for &ldquo;{query}&rdquo;…</>
                  : !found.text_matched ? <>No product name holds a word of &ldquo;{query}&rdquo;, so nothing is shown.</>
                  : found.items.length === 0 ? `Products match “${query}”, but none ${shopperName} can be offered (in the cart, or against their rule).`
                  : `“${query}”: products whose name matches, ranked for ${shopperName} by Aito's purchase ` +
                    "probability × how well the name matches."}
              </div>
              <div className="shop-grid" aria-busy={!found && !searchError}>
                {found?.items.map((item) => (
                  <ProductCard key={item.sku} item={item}
                               onAdd={() => addToCart([item.sku])}
                               onOpen={() => setUrl({ product: item.sku })} />
                ))}
              </div>
            </div>
          ) : (
          <div style={{ minWidth: 0 }}>
            {/* One view per intent (ADR 0033, amendment of 2026-10-21): the routine
                and the kit first, then everything else in "Picked for you". */}
            {suggestionsError && (
              <div className="card card-sub" style={{ color: "var(--red)" }}>
                Couldn&apos;t load their usual basket and kit: {suggestionsError}
              </div>
            )}
            {suggestions && <SuggestionsPanel suggestions={suggestions} month={monthLabel(month)}
                                              onAdd={(sku) => addToCart([sku])} onAddAll={addToCart} />}
            <div className="page-title" style={{ fontSize: 16, margin: "16px 0 4px" }}>Picked for you</div>
            <div className="card-sub" style={{ marginBottom: 8 }}>
              Ranked by Aito for a household with these pets, this month and this cart
            </div>
            {shown?.rescored && (
              <div className="card card-sub" style={{ marginBottom: 8, fontSize: 12 }}>
                <strong>Sandbox, May 2026:</strong> a product whose May state you changed is re-scored, so its
                card shows a score, not a rate.
                <FinePrint>
                  {" "}Aito ranks the top 40 as usual. The score is Aito&apos;s purchase probability × its offer
                  band&apos;s lift × its star band&apos;s lift, both learned by Aito across the whole shop. The
                  multiplication is this app&apos;s modelling choice, not one Aito query.
                </FinePrint>
              </div>
            )}
            <div className="shop-grid" style={{ opacity: stale ? 0.5 : 1 }} aria-busy={!shown || stale}>
              {!shown && Array.from({ length: 8 }, (_, i) => (
                <div key={i} className="card" style={{ height: 170, background: "var(--border-light)" }} />
              ))}
              {shown?.items.map((item, i) => (
                <ProductCard key={item.sku} item={item} rank={i + 1}
                             onAdd={() => addToCart([item.sku])}
                             onOpen={() => setUrl({ product: item.sku })} />
              ))}
            </div>
          </div>
          )}
          <div className="shop-side">
            <CartPanel cart={shown?.cart ?? []} onRemove={(sku) => setCart(cart.filter((s) => s !== sku))}
                       onClear={() => setCart([])} />
          </div>
        </div>
      )}

      {openSku && (
        <ProductDrawer sku={openSku} shopper={shopperKey} month={month} cart={cartParam}
                       onClose={() => setUrl({ product: null })}
                       onAdd={(sku) => addToCart([sku])} onOpen={(sku) => setUrl({ product: sku })} />
      )}
    </div>
  );
}

// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function ShopPage() {
  return (
    <Suspense>
      <ShopView />
    </Suspense>
  );
}
