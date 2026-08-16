# 08 — Agent-mode `status` command & verify

**What to build:** `ghstars status --json`, a single health-check entrypoint reporting last sync time, Retriage Queue count, `Explore: General` (unclassified) count, and a verify pass/fail — so an agent can decide what to do next without pulling full records. (The broader `--json`/`--fields`/hard-fail-under-json contract was established in ticket 01 and inherited by every command since; this ticket is just the new command.)

**Blocked by:** 03, 05.

**Status:** ready-for-agent

- [ ] `ghstars status --json` reports last sync time, Retriage Queue count, unclassified (`Explore: General`) count, and verify pass/fail in one call
- [ ] Verify check is deterministic and offline, mirroring the pattern in the old `gh-stars.py`'s `verify()` function
