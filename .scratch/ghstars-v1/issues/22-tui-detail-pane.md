# 22 — TUI detail pane

**What to build:** a pane showing every field the last `ghstars sync` stored for the Star under the cursor, including `description` and `html_url` — both currently invisible anywhere in the TUI. Spec story 59.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Moving the cursor to a different Star updates the detail pane to that Star's full record
- [x] Every `Star` field the local state store holds is shown somewhere in the pane, not only the fields already in the table
- [x] The pane never blocks the initial paint — it renders from already-loaded local state, no live GitHub call

## Comments

Added a `DetailPane` widget (`src/ghstars/tui/app.py`), composed below the
Star table, wired to `DataTable.RowHighlighted`. It renders every `Star`
field (including `description` and `html_url`) straight from the in-memory
`self._stars`/`self._lists` already loaded by `_reload_local_state()` — no
`GitHubClient` call, so it can never block the initial paint. `pending_list_ids`
shows as "none pending" when null per ADR 0004, with no further special-case
logic. Tests added in `tests/test_tui.py` cover cursor-driven updates, full
field coverage, empty-table placeholder, and rendering before the rate-limit
worker completes.
