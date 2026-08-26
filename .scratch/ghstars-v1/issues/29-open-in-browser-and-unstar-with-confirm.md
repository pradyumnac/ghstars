# 29 — Open in browser, and unstar with confirmation

**What to build:** two single-Star actions on the Star under the cursor. Open: launches the Star's `html_url` via the OS's XDG default handler, using Python's `webbrowser` module — no new dependency. Unstar: opens a confirm dialog before calling `remove_star()` for real; a real, irreversible GitHub mutation must never fire from one keypress. Spec stories 67-68.

**Prefactor first:** `unstar_cmd` (`cli/commands/unstar.py`) currently inlines its lock-load-archive-save orchestration directly in the CLI command, unlike `tag_star()`, which already lives in `ghstars.core` and is shared by the CLI and the TUI. Before this ticket's TUI action exists, extract that orchestration into a new `ghstars.core` function — it already builds on `archive_star()` and `remove_star_from_lists()`, both already in core, so this is a pure move, not new logic. Point `unstar_cmd` at the new function so the CLI's behavior is provably unchanged, then have the TUI call the same function — not a second copy of the same lock/save sequence.

**Blocked by:** 21 (keybind config).

**Status:** done

- [x] A new `ghstars.core` function performs the unstar orchestration (`remove_star()`, then locked archive + list-membership update), used by both `unstar_cmd` and the TUI
- [x] `unstar_cmd`'s existing CLI tests still pass unchanged after the extraction — behavior is provably identical, not just similar
- [x] Pressing the open-in-browser key on the Star under the cursor launches `html_url` via `webbrowser`
- [x] Pressing the unstar key opens a confirm dialog; only confirming calls the new core unstar function
- [x] Cancelling the confirm dialog leaves the Star, local state, and GitHub untouched

## Comments

Prefactor: `unstar_star()` added to a new `ghstars.core.unstar` module —
`client.remove_star()`, then the locked archive + list-membership update,
exactly what `unstar_cmd` (`cli/commands/unstar.py`) used to inline.
`unstar_cmd` now just calls it and translates `GitHubApiError`/`Timeout`
into its existing CLI messages; its own tests pass unchanged. Note:
`pyproject.toml`'s `disallow_any_explicit` mypy override list needed
`ghstars.core.unstar` added — a known mypy/pydantic quirk (see the
comment above that list) that flags every module defining a `BaseModel`
subclass, unrelated to this ticket's logic.

TUI: `o` opens `html_url` via `webbrowser.open()` (no confirm needed,
non-destructive); `u` opens `ConfirmUnstarScreen` (modal, matching
`ListPickerScreen`'s pattern) and only calls `unstar_star()` off the UI
thread if confirmed. Single-Star only (the Star under the cursor), never
the bulk `_selected` set — unstarring several repos from one dialog is a
much bigger blast radius than bulk-tagging. Kept the label "Unstar"
(not "Archive") per spec story 68's own wording and to match the
existing `ghstars unstar` CLI command — flagged and confirmed with the
user before implementing, since "Archive" already means something
different and non-destructive in this domain (story 17's Retired
Category, "without unstarring it").
