# 26 — Grid view mode

**What to build:** a card layout — each Star as a card showing name, language, stargazer count, and description truncated to a fixed character count, so every card stays the same size. Spec story 53.

**Config note:** ticket 23 adds `grid_card_truncation` to `tui.toml`.
This ticket reads that field. It does not define it. Read ADR 0008
first.

**Blocked by:** 25 (reuses the View Mode switcher), 23
(`grid_card_truncation`).

**Status:** ready-for-agent

- [ ] Grid mode is reachable from the same mode-switch key as Folder view
- [ ] Every card is the same size regardless of description length
- [ ] The character limit for a truncated description reads from `grid_card_truncation` in `tui.toml` (ticket 23), never a magic number repeated per card
