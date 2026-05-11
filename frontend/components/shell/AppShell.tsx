"use client";

import type { ReactNode } from "react";

import AitoPanel from "./AitoPanel";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { ShellProvider, useShell } from "./ShellState";


/**
 * Three-pane shell: TopBar fixed at the top, Sidebar fixed on the
 * left, AitoPanel fixed on the right, page content in the middle.
 *
 * Wrapped in `ShellProvider` so child components share collapse /
 * mobile / panel-config state without prop-drilling.
 *
 * Matches `predictive-ecommerce-demo.html` lines 481–516 + 562–566.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <ShellProvider>
      <ShellChrome>{children}</ShellChrome>
    </ShellProvider>
  );
}


function ShellChrome({ children }: { children: ReactNode }) {
  const { sidebarCollapsed, aitoCollapsed, mobileOpen, closeMobile } = useShell();

  const mainClasses = [
    "main",
    sidebarCollapsed ? "sidebar-collapsed" : "",
    aitoCollapsed ? "aito-collapsed" : "",
  ].filter(Boolean).join(" ");

  return (
    <>
      <TopBar />
      {mobileOpen && (
        <div className="pane-overlay visible" onClick={closeMobile} aria-hidden="true" />
      )}
      <div className="layout">
        <Sidebar />
        <main className={mainClasses}>
          {children}
        </main>
        <AitoPanel />
      </div>
    </>
  );
}
