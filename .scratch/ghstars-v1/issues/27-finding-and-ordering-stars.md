# 27 — Finding and ordering Stars: filters, search, sort

**What to build:** filter the visible Stars by Category, Intent, or List; add an Unclassified-only filter (`list_ids` is empty, but the Star is not Archived); search name and description as the user types; and sort by name, star date, stargazer count, language, List count, or List name. Star date descending is the default triage order. Spec stories 54-58.

**Status:** done

- [x] Filter by Category, by Intent, List, Language, License, Owner, Forks, and Followed
- [x] A dedicated "unclassified only" filter in the Filter menu
- [x] Search-as-you-type matches name and description, opened with `/`
- [x] Filter values narrow their options as the user types; recency keeps its shortcut keys
- [x] Sort keys: name, star date, stargazer count, language, List count; any key reversible; star date descending is the default
- [x] Folder-scoped filtering is not required because ticket 25 is retired.
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
value screens narrow their options as the user types. Enter selects the
best-ranked match; Escape cancels the screen. Recency keeps its existing
shortcut keys.
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

**2026-08-26, from a review of commit 99e4174.** Three findings, all
confirmed against HEAD.

Enter now selects the best-ranked match, not a unique match. Commit
99e4174 made this change on purpose. The text above said "unique match"
until this note, so the ticket was stale, not the code. The ranking puts
an exact match first, then a prefix match, then any other substring
match, then alphabetical order.

The clear-filter option was a regression. The parent commit added it,
labelled "All stars", to every value screen unconditionally. Commit
99e4174 added it only when the query held the letters "all", so an
empty query hid it and a query such as "fall" inserted it and then
filtered it out again.

The first fix put it back as an ordinary ranked option. That created a
second bug on a single-option screen (Forks, Followed): the clear
option could sort ahead of the only real option, so Enter on a fresh
screen cleared the filter instead of applying it. The clear option now
always ranks last, so it never steals Enter, and it always shows
without a search.

The label is no longer a generic "All stars". The TUI holds one filter
key, not one per axis, so every clear option clears the whole filter —
`_CLEAR_FILTER_LABELS` names each screen's version of that ("All
categories", "All owners", "Any star date", ...) so the wording matches
the screen the user is on without implying per-axis filtering that
does not exist.

`_match_rank` is now a named helper with its own docstring. The three
boolean sort keys had no explanation, so a later change could reverse
the exact, prefix, and substring precedence without anyone noticing.

- [x] Enter selects the best-ranked match; the ticket text now matches the code
- [x] The clear-filter option appears in every value screen without a search, and never outranks a real option
- [x] The ranking order is a named helper, not three unexplained sort keys
- [x] Tests cover an exact match, a prefix match, multiple matches, zero matches, and an empty query
