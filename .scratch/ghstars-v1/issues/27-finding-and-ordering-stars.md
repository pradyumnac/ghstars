# 27 — Finding and ordering Stars: filters, search, sort

**What to build:** filter the visible Stars by Category, by Intent, or by List; a dedicated filter for unclassified Stars only (empty `list_ids`, not Archived); search-as-you-type on name and description; sort by name, star date, stargazer count, language, or List count, any key reversible, defaulting to star date descending (newest first) — the triage order. A Filter narrows the Stars shown; it works the same whether the current View Mode is flat, grid, or inside a Folder. Spec stories 54-58.

**Blocked by:** 21 (persisted filter/sort state), 25 (story 55 requires filters to compose with Folder scope).

**Status:** partial — Folder integration blocked by ticket 25

- [x] Filter by Category, by Intent, List, Language, License, Owner, Forks, and Followed
- [x] A dedicated "unclassified only" filter in the Filter menu
- [x] Search-as-you-type matches name and description, opened with `/`
- [x] Filter values narrow their options as the user types; recency keeps its shortcut keys
- [x] Sort keys: name, star date, stargazer count, language, List count; any key reversible; star date descending is the default
- [ ] Applying a Filter while inside a Folder narrows that Folder's Stars, without leaving the Folder
- [x] Sort persists into `state/tui-state.toml` (ticket 21) across a quit/relaunch
- [x] Filter state persists into `state/tui-state.toml` across a quit/relaunch

## Comments

**2026-08-26, partial (queued by user ahead of the full ticket):** sort
only, implemented directly on `main` rather than in a worktree, since
it's a small self-contained slice of this ticket. `"s"`
(`action_cycle_sort`, `tui/app.py`) cycles the star table through all
five keys every reversal direction spec story 57 asks for:
`starred_desc` (default) → `name` → `stargazer_desc` → `language` →
`list_count_desc` → back to `starred_desc`. `_sort_status_text()`
renders the whole key map with the active one bracketed
(`Date • [Name] • Stars • Lang • Lists`), shown via `notify()` on every
toggle. Not yet persisted to `state/tui-state.toml` (in-memory/session
only) — the remaining Folder integration is blocked by ticket 25.

**2026-08-26, filters, search, and recency:** `f` opens one Filter menu.
The menu offers Category, Intent, List, Language, License, Recency, Owner,
Forks, Followed, Unclassified, and Clear. Its shortcuts are shown in the
menu; recency offers 1d, 1w, 1m, 3m, 1y, and older-than-1y ranges. Filters
compose with search, update the result count, and persist in
`state/tui-state.toml`. `/` opens the search field, which matches
case-insensitive substrings in the repository name and description. Filter
value screens narrow their options as the user types. Enter selects a unique
match; Escape cancels the screen. Recency keeps its existing shortcut keys.
License now comes from GitHub's `licenseInfo` field and appears in the
DetailPane. Owner, Fork, and Followed filters use fields already in local
state. Archived Stars remain outside the active view.

**2026-08-26, sort persistence:** the active sort key now round-trips
through `state/tui-state.toml`'s existing `sort_key` field (already
speced in ticket 21, just unused until then) -- `TuiApp.__init__`
restores `self._sort_mode` from it (falling back to the default if the
saved value isn't one of this build's `_SORT_MODES`, e.g. after a
downgrade), and `action_cycle_sort` writes it back on every toggle
(in-memory only; `action_quit`'s existing `save_tui_state` call does
the actual disk write). Filter persistence is implemented in `state/tui-state.toml`.

Also added a sixth key, `list_name` (List name ascending, no-Lists
sorted last), beyond this ticket's literal five ("List count", not List
*name*) — per a follow-up user request in the same session. The
Footer's "Sort (...)" label (not a notify toast, per user correction)
tracks the active mode live via `_update_sort_binding_description()`;
every keybinding's Footer description also got a trailing " •"
separator per the same request.
