# 01 — Core scaffolding, fake GitHub client, local state store, CLI skeleton

**What to build:** The seam every other ticket builds on. `ghstars.core` gets its Pydantic models (`Star` with its full field set — full_name, html_url, description, starred_at, first_seen, language, stargazer_count, fork, follow, archived, archived_at, last_checked, list memberships; `List`; `RetriageEntry`; `Nudge`), an abstract GitHub client interface, and an in-memory fake implementing it (the one substituted dependency per the spec's Testing Decisions — no real network calls in tests). A lockfile-guarded local state store under `~/.ghstars/state/` persists `Star`/`List` records. `ghstars.cli` gets its skeleton with `sync` and `list --json` wired against the fake client, establishing from day one: the global `--json` flag, the `--fields` selector, and the hard-fail-instead-of-prompt contract (a missing required decision under `--json` is a non-zero-exit error, never a hang) — every later CLI ticket inherits this, it is not retrofitted afterward. A rate-limit-check stub sits in the fetch path (real enforcement lands with the real client in 02).

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `ghstars.core` exposes `Star`, `List`, `RetriageEntry`, `Nudge` Pydantic models with the full field sets from spec.md's Data model section
- [x] Abstract GitHub client interface defined in `ghstars.core` (fetch stars/lists, create/update/delete list, update list membership for item, remove star)
- [x] In-memory fake client implementing that interface, usable as a test double with no network access
- [x] Local state store under `~/.ghstars/state/` with a lockfile guarding concurrent writes (story 33)
- [x] `ghstars.cli` skeleton with `sync` and `list --json` working end-to-end against the fake client
- [x] `--json` global flag, `--fields` selector, and hard-fail-not-prompt behavior under `--json` all established here (stories 28–30)
- [x] Rate-limit check present in the fetch path (stubbed against the fake; real check lands in 02)
- [x] Tests call `ghstars.core` directly, never through the CLI subprocess, per the spec's Testing Decisions

## Comments

Implemented in commit `3823cc5`. `/code-review` flagged four issues before commit, all fixed:
`--json` was missing from `sync` (added); the fake client didn't keep `List.items`
in sync with `Star.list_ids` on membership/delete/remove-star (fixed, with new
tests); `StateStore` reads weren't lock-guarded and writes weren't atomic (fixed:
reads now take the lock too, writes go through a temp-file + rename); and the
`_star()` test helper was duplicated across three test files (replaced with a
shared `make_star` fixture in `tests/conftest.py`).

Also hit a real tooling incompatibility: `mypy --strict` with `disallow_any_explicit`
flags every `pydantic.BaseModel` subclass (confirmed in an isolated repro,
independent of this project's code, with and without the `pydantic.mypy` plugin).
Resolved with a `[[tool.mypy.overrides]]` scoped to modules that define
BaseModel subclasses — add a module there only when it does the same.
