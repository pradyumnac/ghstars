# 22 — TUI detail pane

**What to build:** a pane showing every field the last `ghstars sync` stored for the Star under the cursor, including `description` and `html_url` — both currently invisible anywhere in the TUI. Spec story 59.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Moving the cursor to a different Star updates the detail pane to that Star's full record
- [ ] Every `Star` field the local state store holds is shown somewhere in the pane, not only the fields already in the table
- [ ] The pane never blocks the initial paint — it renders from already-loaded local state, no live GitHub call
