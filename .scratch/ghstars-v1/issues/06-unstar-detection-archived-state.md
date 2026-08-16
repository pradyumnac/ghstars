# 06 — Unstar detection & Archived state

**What to build:** Handling for the **Star-existence axis** — distinct from the List-membership merge in 05. Sync detects when a repo has been unstarred on GitHub since the last sync and marks the local record `Archived` (a Star property, never an Intent — see CONTEXT.md) rather than deleting it or letting it silently vanish. History for an unstarred repo is never deleted, so the user can still see when and why they once starred it. `ghstars unstar` performs a real unstar against GitHub via a `removeStar` mutation, making the CLI/TUI a real control surface rather than a local shadow copy.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] Sync detects a GitHub-side unstar (repo present in last snapshot, absent from current fetch) and sets `archived`/`archived_at` on the local `Star` record
- [ ] Archived records are never deleted locally; full history remains visible
- [ ] `ghstars unstar <repo>` calls GitHub's `removeStar` mutation and unstars for real
- [ ] Archived is never conflated with Retired (Retired is an Intent value on a List, orthogonal to whether the Star itself is still starred)
