"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { trackEvent } from "@/lib/analytics";
import { VIEWS } from "@/lib/nav";
import { autoStart, choseAView, escapeClosesTour, stepsFor, viewForPath, type Step, type Store } from "@/lib/tour";
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
 * The first-visit tour: three steps, skippable at each, shown once (lib/tour.ts has the rules). The menu step shows the menu: on a phone it
 * opens the drawer, on a desktop with the sidebar collapsed it expands it for the step. The card sits below the drawer (`.tour-card` in
 * globals.css), so it never covers what it points at. Going to another view, or closing the drawer, ends or moves the step on, so the card
 * never describes a menu that is not there. "Take the tour" in the sidebar starts it again.
 */
export default function Tour() {
  const pathname = usePathname();
  const { mobileOpen, sidebarCollapsed, toggleSidebar, previewSidebar, closeMobile, demoMode, demoKnown } = useShell();
  const [steps, setSteps] = useState<Step[]>([]);
  const [index, setIndex] = useState<number | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const expandedByTour = useRef(false);   // the desktop sidebar was collapsed and the menu step showed it, without saving that (previewSidebar)
  const sawDrawerOpen = useRef(false);
  const startedOn = useRef(pathname);
  const latest = useRef({ pathname, mobileOpen, sidebarCollapsed, demoMode });
  latest.current = { pathname, mobileOpen, sidebarCollapsed, demoMode };

  const begin = useCallback((auto: boolean) => {
    const view = viewForPath(latest.current.pathname, VIEWS);
    startedOn.current = latest.current.pathname;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSteps(stepsFor({ view, viewCount: VIEWS.length, touch: isMobile() }));
    setIndex(0);
    trackEvent("tour_started", { view: view?.label ?? latest.current.pathname, auto });
  }, []);

  // First visit: start by itself, once, unless the visitor is being shown the demo (`?demo=` or the server's DEMO_MODE, which may answer late).
  useEffect(() => {
    if (!demoKnown) return;
    const timer = setTimeout(() => {
      if (autoStart({ store: storage(), demoMode: latest.current.demoMode })) begin(true);
    }, AUTO_START_DELAY_MS);
    return () => clearTimeout(timer);
  }, [begin, demoKnown]);

  useEffect(() => {
    const start = () => { closeMobile(); begin(false); };
    window.addEventListener(START_TOUR_EVENT, start);
    return () => window.removeEventListener(START_TOUR_EVENT, start);
  }, [begin, closeMobile]);

  const step = index === null ? null : steps[index];
  const stepId = step?.id;

  const restoreMenu = useCallback(() => {
    if (isMobile() && latest.current.mobileOpen === "sidebar") closeMobile();
    if (expandedByTour.current) {
      expandedByTour.current = false;
      if (!latest.current.sidebarCollapsed) previewSidebar(false);   // still the tour's doing: the visitor has not collapsed it themselves
    }
  }, [closeMobile, previewSidebar]);

  const finish = useCallback((how: "tour_skipped" | "tour_completed", reason?: string) => {
    trackEvent(how, { at_step: index === null ? null : index + 1, of: steps.length, ...(reason ? { reason } : {}) });
    document.querySelectorAll(`.${SPOT}`).forEach((el) => el.classList.remove(SPOT));
    restoreMenu();
    setIndex(null);
    returnFocus.current?.focus();
  }, [index, steps.length, restoreMenu]);

  const go = useCallback((next: number) => {
    setIndex(next);
    trackEvent("tour_step", { step: next + 1, of: steps.length, id: steps[next].id });
  }, [steps]);

  // What the step points at: outlined; the menu step opens the menu where it is not showing, and the next step puts it back.
  useEffect(() => {
    document.querySelectorAll(`.${SPOT}`).forEach((el) => el.classList.remove(SPOT));
    sawDrawerOpen.current = false;
    if (!step) return;
    target(step)?.classList.add(SPOT);
    if (step.id === "menu") {
      if (isMobile() && latest.current.mobileOpen !== "sidebar") toggleSidebar();
      if (!isMobile() && latest.current.sidebarCollapsed) { expandedByTour.current = true; previewSidebar(true); }
    } else {
      restoreMenu();
    }
    card.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepId]);

  // The card's height tells the drawer how much room to leave (`.tour-menu .sidebar` in globals.css).
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("tour-menu", stepId === "menu");
    if (card.current) root.style.setProperty("--tour-card-h", `${card.current.offsetHeight}px`);
    return () => { root.classList.remove("tour-menu"); };
  }, [stepId]);

  // Escape closes the tour wherever the focus is.
  useEffect(() => {
    if (index === null) return;
    const close = (press: KeyboardEvent) => {
      const dialogs = document.querySelectorAll('[role="dialog"]:not(.tour-card)').length;
      if (press.key === "Escape" && escapeClosesTour(dialogs)) finish("tour_skipped", "escape");
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [index, finish]);

  // Tapping a view in the menu ends the tour there. Without this the drawer closing would be read as the visitor moving on to the next step.
  useEffect(() => {
    if (index === null) return;
    const tapped = (tap: MouseEvent) => { if (choseAView(tap.target instanceof Element ? tap.target : null)) finish("tour_skipped", "chose_a_view"); };
    document.addEventListener("click", tapped, true);
    return () => document.removeEventListener("click", tapped, true);
  }, [index, finish]);

  // Going to another view ends the tour: its steps were written for the page it started on.
  useEffect(() => {
    if (index !== null && pathname !== startedOn.current) finish("tour_skipped", "left_the_view");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  // The visitor closed the drawer (the backdrop, or ☰) during the menu step: the menu is no longer what the card describes, so move on.
  useEffect(() => {
    if (stepId !== "menu" || !isMobile() || index === null) return;
    if (mobileOpen === "sidebar") { sawDrawerOpen.current = true; return; }
    if (sawDrawerOpen.current && index < steps.length - 1) go(index + 1);
  }, [mobileOpen, stepId, index, steps.length, go]);

  if (!step || index === null) return null;
  const last = index === steps.length - 1;
  return (
    <div
      className="tour-card" ref={card} role="dialog" aria-labelledby="tour-title" tabIndex={-1}
    >
      <div className="tour-count">{index + 1} of {steps.length}</div>
      <div className="tour-title" id="tour-title">{step.title}</div>
      <div className="tour-text" aria-live="polite">{step.text}</div>
      <div className="tour-actions">
        <button type="button" className="tour-skip" onClick={() => finish("tour_skipped")}>{last ? "Close" : "Skip tour"}</button>
        <button type="button" className="tour-next" onClick={() => (last ? finish("tour_completed") : go(index + 1))}>{last ? "Done" : "Next"}</button>
      </div>
    </div>
  );
}
