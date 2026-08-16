# 05 — Three-way merge & Retriage Queue

**What to build:** Conflict handling for the **List-membership axis** — a Star's Intent/Category classification changing on GitHub and locally since the last sync, distinct from the Star-existence axis (unstar/Archived) covered in 06. Three-way merge per Star, per sync: base (last-synced snapshot) vs. current GitHub state vs. pending local edits. Only one side changed → apply it. Both sides changed to the same result → no-op. Both sides changed to different results → GitHub wins unconditionally; the local pending edit is never applied and never silently dropped — it's written to the local-only Retriage Queue (never a GitHub List) for the user to revisit. No auto-merge/union logic, ever.

**Blocked by:** 04.

**Status:** ready-for-agent

- [ ] All four merge scenarios implemented: local-only change, remote-only change, both-same (no-op), both-different (conflict)
- [ ] On conflict, GitHub's state wins and is applied; the losing local edit is never applied
- [ ] The losing local edit is written to the Retriage Queue, never discarded
- [ ] Retriage Queue is local-only — never synced to GitHub, never a `UserList`
- [ ] `ghstars retriage --json` lists queue contents
- [ ] No auto-merge/union of conflicting classifications anywhere in the path
