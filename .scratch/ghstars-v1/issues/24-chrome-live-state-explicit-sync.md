# 24 — Chrome, live state, and an explicit sync key

**What to build:** the TUI's always-visible state, and the one action that refreshes it for real.

Sizing: configurable header height (tall/short), clock on/off, row height (1 or 2 lines), a star-count column. A top bar shows API rate limit, last sync time, and List count. A bottom status bar shows visible/total Star count, pending-edit count, active sort, and active Filter — sort and Filter shown last, each with its keybind, for example `sort: newest [s]`.

A sync key, distinct from the existing rate-limit-refresh key, runs a full `sync()` with its `on_stage` callback driving a visible progress modal — this implements ADR 0006. ghstars still never syncs except on this explicit keypress. This ticket must also decide, and state in its implementation, what happens to an in-flight selection and any staged `pending_list_ids` while a sync runs, and must stop a second sync from starting mid-flight.

Every new bar shows a labelled placeholder immediately, never a blank strip, per spec story 72. Spec stories 62-66.

**Sizing note:** this ticket bundles what was originally scoped as two — chrome/bars, and the sync key — because the sync key updates the same top bar this ticket builds. If it proves too large for one session, the natural split point is: chrome/bars first, sync key and progress modal second, in that order.

**Blocked by:** 20, 21.

**Status:** ready-for-agent

- [ ] Header height, clock visibility, and row height read from `tui.toml` (ticket 21) and apply on launch
- [ ] Star-count column shown at row height 1; at row height 2, description shows on the second line instead
- [ ] Top bar shows rate limit, last sync time, and List count, each with a labelled placeholder before its first real value arrives
- [ ] Bottom status bar shows "X of Y" Stars, pending-edit count, active sort, active Filter — sort and Filter last, each showing its keybind
- [ ] A sync key runs `ghstars.core.sync.sync()` with `on_stage` driving a progress modal; the key is distinct from the rate-limit-only refresh key
- [ ] Pressing the sync key while a sync is already running does not start a second one
- [ ] The implementation states explicitly what happens to the current selection and any staged `pending_list_ids` during a sync — not left implicit
- [ ] Nothing in this ticket triggers a sync other than the explicit key (ADR 0006)
