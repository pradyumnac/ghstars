# 29 — Open in browser, and unstar with confirmation

**What to build:** two single-Star actions on the Star under the cursor. Open: launches the Star's `html_url` via the OS's XDG default handler, using Python's `webbrowser` module — no new dependency. Unstar: opens a confirm dialog before calling `remove_star()` for real; a real, irreversible GitHub mutation must never fire from one keypress. Spec stories 67-68.

**Prefactor first:** `unstar_cmd` (`cli/commands/unstar.py`) currently inlines its lock-load-archive-save orchestration directly in the CLI command, unlike `tag_star()`, which already lives in `ghstars.core` and is shared by the CLI and the TUI. Before this ticket's TUI action exists, extract that orchestration into a new `ghstars.core` function — it already builds on `archive_star()` and `remove_star_from_lists()`, both already in core, so this is a pure move, not new logic. Point `unstar_cmd` at the new function so the CLI's behavior is provably unchanged, then have the TUI call the same function — not a second copy of the same lock/save sequence.

**Blocked by:** 21 (keybind config).

**Status:** ready-for-agent

- [ ] A new `ghstars.core` function performs the unstar orchestration (`remove_star()`, then locked archive + list-membership update), used by both `unstar_cmd` and the TUI
- [ ] `unstar_cmd`'s existing CLI tests still pass unchanged after the extraction — behavior is provably identical, not just similar
- [ ] Pressing the open-in-browser key on the Star under the cursor launches `html_url` via `webbrowser`
- [ ] Pressing the unstar key opens a confirm dialog; only confirming calls the new core unstar function
- [ ] Cancelling the confirm dialog leaves the Star, local state, and GitHub untouched
