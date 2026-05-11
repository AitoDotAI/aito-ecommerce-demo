"use client";

/** Shared client state for the three-pane shell: sidebar collapse,
 *  Aito-panel collapse, mobile-overlay state, and the per-view
 *  `AitoPanelConfig` the right rail renders.
 *
 *  Lives as a Context so children (TopBar, Sidebar, AitoPanel) can
 *  read + mutate the same state without prop-drilling through
 *  `AppShell`. The values are intentionally minimal — anything
 *  page-specific (page-title, breadcrumb) is set via Context too,
 *  driven by the page's `usePanel()` call inside a `useEffect`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { AitoPanelConfig } from "@/lib/types";

interface ShellState {
  sidebarCollapsed: boolean;
  aitoCollapsed: boolean;
  mobileOpen: "sidebar" | "aito" | null;
  panel: AitoPanelConfig | null;
  pageTitle: string;
  pageDescription: string;
  breadcrumb: string;
}

interface ShellActions {
  toggleSidebar: () => void;
  toggleAito: () => void;
  closeMobile: () => void;
  setPanel: (config: AitoPanelConfig | null) => void;
  setPage: (title: string, description?: string, breadcrumb?: string) => void;
}

const ShellContext = createContext<(ShellState & ShellActions) | null>(null);

const MOBILE_WIDTH = 900;

const isMobile = () =>
  typeof window !== "undefined" && window.innerWidth <= MOBILE_WIDTH;


export function ShellProvider({ children }: { children: ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [aitoCollapsed, setAitoCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState<"sidebar" | "aito" | null>(null);
  const [panel, setPanel] = useState<AitoPanelConfig | null>(null);
  const [pageTitle, setPageTitle] = useState("Dashboard");
  const [pageDescription, setPageDescription] = useState(
    "Predictive insights from your purchase data — updated on every query.",
  );
  const [breadcrumb, setBreadcrumb] = useState("Dashboard");

  // Persist desktop collapse state so a refresh doesn't surprise
  // the visitor. Mobile drawer state stays ephemeral.
  useEffect(() => {
    if (isMobile()) return;
    const sb = localStorage.getItem("ecom.sidebarCollapsed");
    const ap = localStorage.getItem("ecom.aitoCollapsed");
    if (sb === "true") setSidebarCollapsed(true);
    if (ap === "true") setAitoCollapsed(true);
  }, []);

  const toggleSidebar = useCallback(() => {
    if (isMobile()) {
      setMobileOpen((prev) => (prev === "sidebar" ? null : "sidebar"));
    } else {
      setSidebarCollapsed((prev) => {
        const next = !prev;
        localStorage.setItem("ecom.sidebarCollapsed", String(next));
        return next;
      });
    }
  }, []);

  const toggleAito = useCallback(() => {
    if (isMobile()) {
      setMobileOpen((prev) => (prev === "aito" ? null : "aito"));
    } else {
      setAitoCollapsed((prev) => {
        const next = !prev;
        localStorage.setItem("ecom.aitoCollapsed", String(next));
        return next;
      });
    }
  }, []);

  const closeMobile = useCallback(() => setMobileOpen(null), []);

  const setPage = useCallback((title: string, description?: string, breadcrumbLabel?: string) => {
    setPageTitle(title);
    if (description != null) setPageDescription(description);
    setBreadcrumb(breadcrumbLabel ?? title);
  }, []);

  const value = useMemo<ShellState & ShellActions>(() => ({
    sidebarCollapsed,
    aitoCollapsed,
    mobileOpen,
    panel,
    pageTitle,
    pageDescription,
    breadcrumb,
    toggleSidebar,
    toggleAito,
    closeMobile,
    setPanel,
    setPage,
  }), [
    sidebarCollapsed, aitoCollapsed, mobileOpen, panel,
    pageTitle, pageDescription, breadcrumb,
    toggleSidebar, toggleAito, closeMobile, setPage,
  ]);

  return <ShellContext.Provider value={value}>{children}</ShellContext.Provider>;
}


export function useShell(): ShellState & ShellActions {
  const v = useContext(ShellContext);
  if (!v) {
    throw new Error("useShell must be used inside <ShellProvider>");
  }
  return v;
}


/** Per-page hook: bind the page's `AitoPanelConfig`, title,
 *  description, and breadcrumb at mount, and clear (panel only)
 *  on unmount. */
export function usePagePanel(
  config: AitoPanelConfig | null,
  page: { title: string; description?: string; breadcrumb?: string },
) {
  const { setPanel, setPage } = useShell();
  useEffect(() => {
    setPanel(config);
    setPage(page.title, page.description, page.breadcrumb);
    return () => {
      // Leave the panel populated on navigation — the next page
      // sets its own immediately, and clearing here causes a
      // mid-route flash of empty panel.
    };
    // panel/page identity is captured at mount; pages that need
    // to update dynamically can call setPanel/setPage themselves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
