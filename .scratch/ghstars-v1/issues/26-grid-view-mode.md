# 26 — Grid view mode

**What to build:** a card layout — each Star as a card showing name, language, stargazer count, and description truncated to a fixed character count, so every card stays the same size. Spec story 53.

**Blocked by:** 25 (reuses the View Mode switcher).

**Status:** ready-for-agent

- [ ] Grid mode is reachable from the same mode-switch key as Folder view
- [ ] Every card is the same size regardless of description length
- [ ] The character limit for a truncated description is a named constant, not a magic number repeated per card
