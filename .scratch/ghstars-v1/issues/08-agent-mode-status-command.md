# 08 — Agent-mode `status` command & verify

**What to build:** `ghstars status --json`, a single health-check entrypoint reporting last sync time, Retriage Queue count, `Explore: General` (unclassified) count, and a verify pass/fail — so an agent can decide what to do next without pulling full records. (The broader `--json`/`--fields`/hard-fail-under-json contract was established in ticket 01 and inherited by every command since; this ticket is just the new command.)

**Blocked by:** 03, 05, 19.

**Status:** done

- [x] `ghstars status --json` reports last sync time, Retriage Queue count, unclassified (`Explore: General`) count, and verify pass/fail in one call
- [x] Verify check is deterministic and offline, mirroring the pattern in the old `gh-stars.py`'s `verify()` function

## Comments

- **"Last sync time" derivation:** confirmed by reading `sync.py` that there is no dedicated sync-timestamp field or file anywhere in local state — `Star.last_checked` is the only time-of-fetch signal, and it's per-star. `ghstars status` derives `last_sync_at` as `max(star.last_checked for star in stars)`, `None` when there are no stars yet (i.e. before the first `sync`). This is what `sync()` stamps on every `Star` it fetches, so the max across all stars is exactly "when did the most recent sync last touch local state."
- **Verify-check interpretation:** read the old `gh-stars.py`'s `verify()` (`/home/doe/repos/notes/scripts/gh-stars.py:336`) for the pattern to mirror: a flat list of problem strings, deterministic and offline, checking internal consistency of the local JSON snapshot (duplicate identifiers, dangling references, `_meta` counts that don't match the data). Adapted to ghstars' `stars.json`/`lists.json` shape, `verify_state(stars, lists)` (`src/ghstars/core/status.py`) checks three things:
  1. No duplicate `Star.full_name` in `stars.json`.
  2. No duplicate `List.id` in `lists.json`.
  3. No `Star.list_ids` entry naming a `List.id` absent from `lists.json`.

  Deliberately does *not* flag a `List.items` entry with no matching Star, or a `List.malformed=True` List: both are already-documented, self-healing, non-corrupt states per `reconcile_list_membership`'s and `List.malformed`'s own docstrings, not structural damage — flagging them would make `verify` cry wolf on ordinary transient states a normal `sync()` already tolerates.
- Implementation: `src/ghstars/core/status.py` (`StatusReport`, `build_status`, `verify_state`), `src/ghstars/cli/commands/status.py` (`ghstars status --json`), registered in `src/ghstars/cli/commands/__init__.py`. Promoted `sync.py`'s `_EXPLORE_GENERAL` to a public `EXPLORE_GENERAL` (code-review finding: a private name was becoming a cross-module dependency).
- Tests: `tests/test_cli_status.py` — happy path with mixed classified/unclassified/retriage state, empty/never-synced state, and verify pass/fail including a dangling `list_ids` reference.
