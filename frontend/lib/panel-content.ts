/** Per-view Aito-panel content.
 *
 * The right-rail panel is the single highest-leverage piece of
 * marketing copy in the demo: it's where a CTO reads the actual
 * Aito query that's driving what they see on the page.
 *
 * Pages call e.g. `dashboardPanel()` to get their config. Click
 * handlers within a page may override on selection — that stays
 * per-page.
 *
 * Builders are added here as each view lands. Build order is in
 * TASK.md; the scaffold step ships none — the full layout shell
 * (with the AitoPanel component) lands in step 4.
 *
 * Every query rendered MUST be runnable against the live PetNord
 * data. No aspirational queries (CLAUDE.md prime directive #2).
 */

import type { AitoPanelConfig } from "./types";

// Page-specific panel builders go here as views land.
// Example signature (reference, not yet wired):
//
//   export function dashboardPanel(): AitoPanelConfig { … }

export type { AitoPanelConfig };
