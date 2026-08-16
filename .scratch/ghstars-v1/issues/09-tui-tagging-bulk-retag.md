# 09 — TUI: interactive tagging, bulk tagging, retagging

**What to build:** A Textual TUI, a thin wrapper over `ghstars.core`, for fast interactive triage: tag a single Star, bulk-tag a batch, and retag (move a Star between Categories or Intents as usage evolves) without leaving the terminal. Each List's public/private status is shown explicitly, so a private List is never mistaken for a public one.

**Blocked by:** 04.

**Status:** ready-for-agent

- [ ] TUI supports single-item tagging against `ghstars.core`
- [ ] TUI supports bulk tagging across a selected batch of Stars
- [ ] TUI supports retagging (moving a Star between Category/Intent)
- [ ] Each List's public/private status is visibly and unambiguously displayed
