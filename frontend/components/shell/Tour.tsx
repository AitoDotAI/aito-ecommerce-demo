"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { trackEvent } from "@/lib/analytics";
import { VIEWS } from "@/lib/nav";
import { markSeen, shouldAutoStart, stepsFor, viewForPath, type Step, type Store } from "@/lib/tour";
import { isMobile, useShell } from "./ShellState";

export const START_TOUR_EVENT = "ecom:start-tour";
const SPOT = "tour-spot";
const AUTO_START_DELAY_MS = 900;

/** `localStorage`, or nothing where reading it throws (private window, blocked site data). */
function storage(): Store | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

/** The element a step points at, if it has one: the menu, or the button that opens the queries behind a number. */
function target(step: Step): Element | null {
  if (step.id === "menu") return document.querySelector(".sidebar");
  if (step.id === "why") return document.querySelector(isMobile() ? ".aito-mobile-fab" : ".aito-panel-toggle");
  return null;
}

/**
 * The first-visit tour: three steps, skippable at each, shown once (lib/tour.ts has the rules). On a phone the menu step opens
 * the drawer, and the card sits below it (see `.tour-card` in globals.css), so it never covers what it points at.
 * "Take the tour" in the sidebar starts it again.
 */
export default function Tour() {
  const pathname = usePathname();
  const { mobileOpen, toggleSidebar, closeMobile, demoMode } = useShell();
  const [steps, setSteps] = useState<Step[]>([]);
  const [index, setIndex] = useState<number | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const latest = useRef({ pathname, mobileOpen, demoMode });
  latest.current = { pathname, mobileOpen, demoMode };

  const begin = useCallback((auto: boolean) => {
    const view = viewForPath(latest.current.pathname, VIEWS);
    setSteps(stepsFor({ view, viewCount: VIEWS.length }));
    setIndex(0);
    trackEvent("tour_started", { view: view?.label ?? latest.current.pathname, auto });
  }, []);

  // First visit: start by itself, once, unless the visitor is being shown the demo (`?demo=`).
  useEffect(() => {
    const timer = setTimeout(() => {
      if (latest.current.demoMode || !shouldAutoStart(storage())) return;
      markSeen(storage());
      begin(true);
    }, AUTO_START_DELAY_MS);
    return () => clearTimeout(timer);
  }, [begin]);

  useEffect(() => {
    const start = () => { closeMobile(); begin(false); };
    window.addEventListener(START_TOUR_EVENT, start);
    return () => window.removeEventListener(START_TOUR_EVENT, start);
  }, [begin, closeMobile]);

  const step = index === null ? null : steps[index];
  const stepId = step?.id;

  // What the step points at: outlined, and on a phone the menu step opens the drawer (and the next one closes it).
  useEffect(() => {
    document.querySelectorAll(`.${SPOT}`).forEach((el) => el.classList.remove(SPOT));
    if (!step) return;
    target(step)?.classList.add(SPOT);
    const open = latest.current.mobileOpen === "sidebar";
    if (isMobile() && step.id === "menu" && !open) toggleSidebar();
    if (isMobile() && step.id !== "menu" && open) closeMobile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepId]);

  // The card's height tells the drawer how much room to leave (`.tour-menu .sidebar` in globals.css).
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("tour-menu", stepId === "menu");
    if (card.current) root.style.setProperty("--tour-card-h", `${card.current.offsetHeight}px`);
    return () => { root.classList.remove("tour-menu"); };
  }, [stepId]);

  const finish = useCallback((how: "tour_skipped" | "tour_completed") => {
    trackEvent(how, { at_step: index === null ? null : index + 1, of: steps.length });
    document.querySelectorAll(`.${SPOT}`).forEach((el) => el.classList.remove(SPOT));
    if (isMobile() && latest.current.mobileOpen === "sidebar") closeMobile();
    setIndex(null);
  }, [index, steps.length, closeMobile]);

  const go = (next: number) => {
    setIndex(next);
    trackEvent("tour_step", { step: next + 1, of: steps.length, id: steps[next].id });
  };

  if (!step || index === null) return null;
  const last = index === steps.length - 1;
  return (
    <div className="tour-card" ref={card} role="dialog" aria-label="Tour of the demo" aria-live="polite">
      <div className="tour-count">{index + 1} of {steps.length}</div>
      <div className="tour-title">{step.title}</div>
      <div className="tour-text">{step.text}</div>
      <div className="tour-actions">
        <button type="button" className="tour-skip" onClick={() => finish("tour_skipped")}>{last ? "Close" : "Skip tour"}</button>
        <button type="button" className="tour-next" onClick={() => (last ? finish("tour_completed") : go(index + 1))}>{last ? "Done" : "Next"}</button>
      </div>
    </div>
  );
}
