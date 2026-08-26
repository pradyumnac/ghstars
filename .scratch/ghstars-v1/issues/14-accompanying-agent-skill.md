# 14 — Accompanying agent skill (replaces `github-stars`)

**What to build:** The agent skill shipped alongside ghstars, mirroring the existing `github-stars` skill's structure, documenting the deterministic/agentic division of labor for driving `ghstars.cli`: sync, tag, retriage review, unstar, category rename/drain, status, export, diff, and nudge recording. This skill is meant to replace `github-stars` once ghstars is stable — but the *mechanism* for retiring/superseding `github-stars` within the user's AI-stowing system (how an old skill gets decommissioned, whether it's deleted vs. archived vs. redirected) is an open question, deliberately **not resolved by this ticket**. Implement the new skill; park the retirement mechanism as a followup once this ticket is picked up.

**Blocked by:** 12, 30.

**Status:** ready-for-agent

- [ ] Skill documents the deterministic/agentic division of labor for: sync, tag, retriage, unstar, category rename/drain, status, export, diff, nudges
- [ ] Skill structure mirrors the existing `github-stars` skill
- [ ] Skill is vendored the same way `github-stars` is today
- [ ] The `github-stars` → `ghstars` retirement mechanism is explicitly called out as unresolved, not silently decided in this ticket
