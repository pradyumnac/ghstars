# 11 — State diff

**What to build:** `ghstars diff` wraps `git diff`/`git log -p` against `state/`'s repo when the user has git-tracked `~/.ghstars/state/` themselves, giving a clear "no git history available" message otherwise. ghstars never runs `git init` and never auto-commits `state/` on its own — tracking and committing that directory is entirely the user's choice and responsibility. No bespoke diff engine.

**Blocked by:** 04.

**Status:** done

- [x] `ghstars diff` shows a diff of classification changes via `git diff`/`git log -p` when `state/` is already a git repo
- [x] Clear, non-crashing message when `state/` is not git-tracked
- [x] ghstars never runs `git init` on `state/`
- [x] ghstars never auto-commits `state/`, under any condition

## Comments

Triage completed. The implementation and tests meet all acceptance criteria.

Verification: `uv run pytest tests/test_cli_diff.py` passed: 9 tests.
