# 11 — State diff

**What to build:** `ghstars diff` wraps `git diff`/`git log -p` against `state/`'s repo when the user has git-tracked `~/.ghstars/state/` themselves, giving a clear "no git history available" message otherwise. ghstars never runs `git init` and never auto-commits `state/` on its own — tracking and committing that directory is entirely the user's choice and responsibility. No bespoke diff engine.

**Blocked by:** 04.

**Status:** ready-for-agent

- [ ] `ghstars diff` shows a diff of classification changes via `git diff`/`git log -p` when `state/` is already a git repo
- [ ] Clear, non-crashing message when `state/` is not git-tracked
- [ ] ghstars never runs `git init` on `state/`
- [ ] ghstars never auto-commits `state/`, under any condition
