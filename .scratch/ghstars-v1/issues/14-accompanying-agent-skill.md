# 14 — Accompanying agent skill (replaces `github-stars`)

**What to build:** Ship an agent skill with ghstars. Mirror the existing
`github-stars` skill structure. Document how agents use `ghstars.cli` for sync,
tag, retriage review, unstar, category rename or drain, status, export, and
diff.

When the agent notices relevant workflow friction, it tells the user directly
as a plain observation. It does not persist, deduplicate, or apply
observations.

This skill replaces `github-stars` when ghstars is stable. This ticket does not
decide how to retire the old skill in the AI-stowing system. Record that
question as a follow-up when work starts.

**Blocked by:** 30.

**Status:** ready-for-agent

- [ ] Skill documents the deterministic/agentic division of labor for: sync, tag, retriage, unstar, category rename/drain, status, export, and diff
- [ ] Skill tells the user about relevant workflow friction as a plain observation
- [ ] Skill does not persist, deduplicate, or apply observations
- [ ] Skill structure mirrors the existing `github-stars` skill
- [ ] Skill is vendored the same way `github-stars` is today
- [ ] The `github-stars` → `ghstars` retirement mechanism is explicitly called out as unresolved, not silently decided in this ticket
