# 27 — Finding and ordering Stars: filters, search, sort

**What to build:** filter the visible Stars by Category, by Intent, or by List; a dedicated filter for unclassified Stars only (empty `list_ids`, not Archived); search-as-you-type on name and description; sort by name, star date, stargazer count, language, or List count, any key reversible, defaulting to star date descending (newest first) — the triage order. A Filter narrows the Stars shown; it works the same whether the current View Mode is flat, grid, or inside a Folder. Spec stories 54-58.

**Blocked by:** 21 (persisted filter/sort state), 25 (story 55 requires filters to compose with Folder scope).

**Status:** ready-for-agent

- [ ] Filter by Category, by Intent, and by List, each reachable by its own key
- [ ] A dedicated "unclassified only" filter
- [ ] Search-as-you-type matches name and description, opened with `/`
- [x] Sort keys: name, star date, stargazer count, language, List count; any key reversible; star date descending is the default
- [ ] Applying a Filter while inside a Folder narrows that Folder's Stars, without leaving the Folder
- [x] Sort persists into `state/tui-state.toml` (ticket 21) across a quit/relaunch (Filter persistence still open -- no Filter exists yet)

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
only) — this ticket's own AC still requires that, along with every
filter/search AC, none of which are implemented. Status stays
`ready-for-agent`, not `done`.

**2026-08-26, sort persistence:** the active sort key now round-trips
through `state/tui-state.toml`'s existing `sort_key` field (already
speced in ticket 21, just unused until now) -- `TuiApp.__init__`
restores `self._sort_mode` from it (falling back to the default if the
saved value isn't one of this build's `_SORT_MODES`, e.g. after a
downgrade), and `action_cycle_sort` writes it back on every toggle
(in-memory only; `action_quit`'s existing `save_tui_state` call does
the actual disk write). Filter persistence is still open -- there is no
Filter feature yet to persist.

Also added a sixth key, `list_name` (List name ascending, no-Lists
sorted last), beyond this ticket's literal five ("List count", not List
*name*) — per a follow-up user request in the same session. The
Footer's "Sort (...)" label (not a notify toast, per user correction)
tracks the active mode live via `_update_sort_binding_description()`;
every keybinding's Footer description also got a trailing " •"
separator per the same request.
