# 27 — Finding and ordering Stars: filters, search, sort

**What to build:** filter the visible Stars by Category, by Intent, or by List; a dedicated filter for unclassified Stars only (empty `list_ids`, not Archived); search-as-you-type on name and description; sort by name, star date, stargazer count, language, or List count, any key reversible, defaulting to star date descending (newest first) — the triage order. A Filter narrows the Stars shown; it works the same whether the current View Mode is flat, grid, or inside a Folder. Spec stories 54-58.

**Blocked by:** 21 (persisted filter/sort state), 25 (story 55 requires filters to compose with Folder scope).

**Status:** ready-for-agent

- [ ] Filter by Category, by Intent, and by List, each reachable by its own key
- [ ] A dedicated "unclassified only" filter
- [ ] Search-as-you-type matches name and description, opened with `/`
- [ ] Sort keys: name, star date, stargazer count, language, List count; any key reversible; star date descending is the default
- [ ] Applying a Filter while inside a Folder narrows that Folder's Stars, without leaving the Folder
- [ ] Active Filter and sort persist into `state/tui-state.toml` (ticket 21) across a quit/relaunch
