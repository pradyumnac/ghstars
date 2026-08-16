# 01 — Core scaffolding, fake GitHub client, local state store, CLI skeleton

**What to build:** The seam every other ticket builds on. `ghstars.core` gets its Pydantic models (`Star` with its full field set — full_name, html_url, description, starred_at, first_seen, language, stargazer_count, fork, follow, archived, archived_at, last_checked, list memberships; `List`; `RetriageEntry`; `Nudge`), an abstract GitHub client interface, and an in-memory fake implementing it (the one substituted dependency per the spec's Testing Decisions — no real network calls in tests). A lockfile-guarded local state store under `~/.ghstars/state/` persists `Star`/`List` records. `ghstars.cli` gets its skeleton with `sync` and `list --json` wired against the fake client, establishing from day one: the global `--json` flag, the `--fields` selector, and the hard-fail-instead-of-prompt contract (a missing required decision under `--json` is a non-zero-exit error, never a hang) — every later CLI ticket inherits this, it is not retrofitted afterward. A rate-limit-check stub sits in the fetch path (real enforcement lands with the real client in 02).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `ghstars.core` exposes `Star`, `List`, `RetriageEntry`, `Nudge` Pydantic models with the full field sets from spec.md's Data model section
- [ ] Abstract GitHub client interface defined in `ghstars.core` (fetch stars/lists, create/update/delete list, update list membership for item, remove star)
- [ ] In-memory fake client implementing that interface, usable as a test double with no network access
- [ ] Local state store under `~/.ghstars/state/` with a lockfile guarding concurrent writes (story 33)
- [ ] `ghstars.cli` skeleton with `sync` and `list --json` working end-to-end against the fake client
- [ ] `--json` global flag, `--fields` selector, and hard-fail-not-prompt behavior under `--json` all established here (stories 28–30)
- [ ] Rate-limit check present in the fetch path (stubbed against the fake; real check lands in 02)
- [ ] Tests call `ghstars.core` directly, never through the CLI subprocess, per the spec's Testing Decisions
