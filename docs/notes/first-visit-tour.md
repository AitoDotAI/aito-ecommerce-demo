# The first-visit tour

A phone visitor who lands on a deep link (say `/retention/`) sees one view and a ☰ button; the menu with the other 18 views is behind it. The tour is three skippable steps, shown once:
what this is (or, on a deep link, "You are on <view>"), the menu (opened on a phone), and the Why / the Aito button.

- **Rules:** `frontend/lib/tour.ts`, without React, tested by `frontend/tests/tour.test.mts` (`./do frontend-test`, and in CI). The seen flag is `localStorage` `ecom.tourSeen`, set when the tour starts; where storage is missing or throws, the tour does not start by itself (it could not remember being dismissed), and the page works as before.
- **Card:** `frontend/components/shell/Tour.tsx`, styled in `globals.css` (`.tour-card`). On a phone it sits above the Aito button, and on the menu step the drawer is cut short by the card's height, so the card never covers what it points at. Not shown when `?demo=` presents the demo.
- **Again:** "Take the tour" at the foot of the sidebar fires `ecom:start-tour`.
- **Events:** `tour_started` (view, auto), `tour_step`, `tour_skipped` (at_step), `tour_completed`; every event now also carries `device` (`mobile` at 900 px or narrower, else `desktop`), so views per session for phone visitors can be compared before and after the tour.
- **Reuse:** the rules take their views and storage key as inputs; a sibling demo copies `lib/tour.ts`, `Tour.tsx` and the CSS block and passes its own views. Next: accounting, ERP, SQL, agent, equity demos (not done).
