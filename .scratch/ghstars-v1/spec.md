Status: ready-for-agent

# ghstars — v1 spec

## Problem Statement

The user has hundreds of GitHub starred repos and no systematic way to classify them. Their existing tool (`gh-stars.py` + the `github-stars` skill) only produces a flat, unclassified markdown reference table — it fetches and renders, but has no concept of grouping, adoption status, or triage. New stars pile up undifferentiated; there's no way to tell "things I actively use" from "things I'm evaluating" from "things I keep purely for reference," and no way to drive that classification from a script or an agent, only by hand.

The user also stars and reorganizes from their phone and the GitHub web UI, so any classification system that only lives locally will drift out of sync with what's actually true on GitHub.

## Solution

`ghstars` is a terminal-first tool (TUI + CLI) that classifies starred repos into Lists, using GitHub's own native Lists feature (`UserList` in GitHub's GraphQL API) as the synced, authoritative backing store rather than inventing a parallel local taxonomy. Classification is encoded directly in List names via an `Intent` prefix (`Explore` / `Current` / `Retired` / `Reference`) plus a freeform `Category`, so the taxonomy is visible and usable from github.com, the phone app, or ghstars itself — with no separate system to keep manually consistent.

A Textual TUI supports fast interactive tagging, bulk tagging, and retagging. A Typer CLI, including a dedicated token-efficient agent/JSON mode, supports scripting and lets an accompanying agent skill drive and monitor ghstars the same way the existing `github-stars` skill drives `gh-stars.py` today. Sync is two-way: GitHub is the sole source of truth for List existence and membership (see ADR 0001); anything GitHub's schema can't represent (conflict handling, sync history, export config) lives in a local `~/.ghstars/` tree (see ADR 0002), git-diffable but never auto-git-initialized.

The old `gh-stars.py` script and `github-stars` skill are retired once ghstars replaces them.

## User Stories

### Fetch & sync

1. As a developer, I want ghstars to fetch all my starred repos from GitHub, so that I have an up-to-date local view of everything I've starred.
2. As a developer, I want ghstars to fetch my existing GitHub Lists and their membership, so that classification I've already done on github.com is respected, not overwritten.
3. As a developer, I want newly starred repos (starred from my phone or the GitHub web UI) pulled in automatically on the next sync, so that I never have to remember to add them manually.
4. As a developer, I want unclassified new stars to land in `Explore: General` by default, so that nothing slips through without at least a landing spot.
5. As a developer, I want ghstars to detect when I've unstarred a repo on GitHub, so that its local record is marked Archived rather than silently vanishing.
6. As a developer, I want ghstars to never delete history for an unstarred repo, so that I can still see when and why I once starred something.
7. As a developer, I want local retagging changes to sync out to GitHub, so that my phone/web view of my Lists matches what I did in the TUI/CLI.
8. As a developer, I want unstarring a repo locally in ghstars to actually unstar it on GitHub, so that the CLI/TUI is a real control surface, not just a local shadow copy.
9. As a developer, I want a sync to detect when a Star's List membership changed both locally and on GitHub since the last sync, so that I don't silently lose one side's change.
10. As a developer, I want GitHub to always win on a detected conflict, so that whatever I check from any device is never surprised by a local override.
11. As a developer, I want the local edit that lost a conflict to land in a Retriage Queue instead of being discarded, so that I can revisit and re-decide rather than losing my intent entirely.
12. As a developer, I want the Retriage Queue to be purely local, not a GitHub List, so that in-progress conflict handling never leaks onto a public list or costs extra API calls.
13. As a developer, I want a rate-limit check before any fetch begins, so that a large sync doesn't get stuck mid-way and leave state half-updated.
14. As a developer, I want fetches batched via paginated GraphQL rather than per-repo calls, so that syncing hundreds of stars doesn't burn through my API quota.

### Taxonomy

15. As a developer, I want to classify a Star using `Explore`, `Current`, `Retired`, or `Reference` Intent prefixes on List names, so that the List name itself fully encodes my relationship to that Category.
16. As a developer, I want `Explore`, `Current`, and `Retired` to be mutually exclusive per Category, so that a Star's adoption status for a given Category is always unambiguous.
17. As a developer, I want to move a Star from `Current` to `Retired` without unstarring it, so that I can keep a record of things I used to rely on without cluttering my active tool lists.
18. As a developer, I want `Reference` Lists to have no adoption lifecycle, so that informational collections (e.g. "Reference: AI Agents") aren't forced into a Current/Explore choice that doesn't apply.
19. As a developer, I want General Lists with no Intent prefix, so that Lists outside the tool-adoption domain aren't forced into this taxonomy.
20. As a developer, I want to add new Categories on demand, so that my taxonomy can grow as my interests do.
21. As a developer, I want to rename a Category and have all its Lists (across Intents) renamed consistently, so that I don't have to manually update Current/Explore/Retired variants separately.
22. As a developer, I want to "drain" (bulk-migrate) all Stars from one Category into another, so that I can reorganize my taxonomy without manually moving each Star.
23. As a developer, I want ghstars to validate that List names conform to the `{Intent}: {Category}` convention (or are recognized as General), so that a malformed name doesn't silently break sync or export.

### TUI

24. As a developer, I want a TUI for fast interactive tagging, so that I can quickly triage a batch of unclassified stars without leaving the terminal.
25. As a developer, I want bulk tagging in the TUI, so that reclassifying many repos at once doesn't require repetitive single-item actions.
26. As a developer, I want retagging support in the TUI, so that I can move a Star between Categories or Intents as my usage of it evolves.
27. As a developer, I want the TUI to show each List's public/private status explicitly, so that I never mistake a private List for a public one or vice versa.

### CLI & agent integration

28. As an agent driving ghstars via scripts, I want a `--json` flag on every subcommand, so that I get structured, parseable output instead of scraping human-formatted text.
29. As an agent, I want a `--fields` selector on list-returning commands, so that I only pay the token cost for the fields I actually need.
30. As an agent, I want agent-mode output to never include interactive prompts, so that a missing required decision fails hard with a clear error instead of hanging.
31. As an agent, I want a single `ghstars status --json` command reporting last sync time, Retriage Queue count, and unclassified-star count, so that I can decide what to do next without pulling full records.
32. As an agent, I want write operations to be idempotent where feasible, so that retrying a call after a timeout doesn't manufacture a spurious conflict against my own prior attempt.
33. As a developer running concurrent ghstars invocations (human + agent, or two agent sessions), I want a local lockfile around state writes, so that concurrent operations never corrupt local state.

### Export

34. As a developer, I want to define a generic mapping from a List (or Category) to an output file and format, so that I can drive my own downstream pipelines (`tools.yaml`, skill vendor lists) without ghstars hardcoding my specific use cases.
35. As a developer, I want to ask "what tools am I currently exploring but haven't tried yet," so that I have an easy on-ramp into repos I starred but never followed up on.

### State & diffing

36. As a developer, I want ghstars to never auto-commit `state/`, so that I retain full control over when history is recorded — even when `state/` is already a git repo, committing stays my responsibility, not ghstars'.
37. As a developer, I want ghstars to never run `git init` on its own, so that git-tracking `state/` is something I opt into deliberately, not an unrequested side effect.
38. As a developer, I want a `ghstars diff` command, so that I (or an agent) can see exactly what changed in my classification since the last sync.
39. As a developer, I want `config/` to stay plain files, never auto-committed by ghstars, so that stowing it into my dotfiles repo doesn't create a nested-repo conflict.

### Nudges

40. As a developer, I want the accompanying agent skill to record "nudges" — observations about workflow friction — without acting on them, so that I retain full control over whether to actually change my config or workflow.
41. As a developer, I want nudges deduplicated by a stable key, so that repeated friction doesn't spam me with duplicate notes.
42. As a developer, I want nudge surfacing off by default, so that this feature doesn't clutter normal usage until I've opted in.
43. As a developer, I want nudges to never appear in `--json`/agent-mode output, so that they don't undercut the token-efficiency the CLI's agent mode is meant to provide.
44. As an agent, I want to only read the nudge files when I have something new to record, so that normal operation doesn't pay the token cost of loading nudge state on every call.

### Distribution & retirement

45. As a developer, I want ghstars installable via `uv tool install`, PyPI, and GitHub Releases with per-platform tar.gz binaries, so that I have flexible install paths from day one.
46. As a developer, I want an accompanying agent skill shipped alongside ghstars, mirroring the existing `github-stars` skill's structure, so that Claude and other agents know how to drive and monitor it correctly.
47. As a developer, I want the old `gh-stars.py` script and `github-stars` skill retired once ghstars is stable, so that I'm not maintaining two overlapping GitHub-stars fetchers.

### Privacy

48. As a developer, I want new Lists to default to public, matching my existing Lists, with an explicit `isPrivate` override available per List, so that I can keep sensitive groupings private without changing my established default.

### TUI (addendum)

49. As a developer, I want the TUI to show my remaining GitHub API rate limit, so that I can tell when I'm approaching a sync-blocking limit before it happens. Numbered out of sequence with the rest of the TUI section (24-27) to avoid renumbering every other story's cross-references elsewhere in this doc and the codebase.

## Implementation Decisions

**Modules**

- `ghstars.core` — the single test seam. Pydantic data models, the sync engine (fetch/merge/conflict/push), taxonomy validation, the export engine, an abstract GitHub client interface, the local state store, the Retriage Queue, and the nudge store.
- `ghstars.github` — the concrete GitHub API client, implementing `ghstars.core`'s abstract client interface over `gh api graphql`.
- `ghstars.cli` — Typer CLI, a thin wrapper over `ghstars.core`. Owns `--json`/`--fields`/agent-mode conventions.
- `ghstars.tui` — Textual TUI, a thin wrapper over `ghstars.core`.
- Accompanying agent skill (separate deliverable, vendored the same way `github-stars` is today) — documents the deterministic/agentic division of labor below for agents driving `ghstars.cli`.

**Data model (Pydantic)**

- `Star`: full_name, html_url, description, starred_at, first_seen, language, stargazer_count, fork, follow, archived, archived_at, last_checked, list memberships.
- `List`: id (GitHub node ID), name, slug, description, is_private, intent (`Explore`/`Current`/`Retired`/`Reference`/`None` for General), category, items.
- `RetriageEntry`: star full_name, attempted list change, conflict detected at, resolved (bool).
- `Nudge`: stable slug/key, theme, message, count, last_seen.
- No separate sync-log schema — `state/`'s git commits (when present) serve this role; no bespoke log format to design or maintain.

**GitHub API contract (GraphQL)**

- Read: `viewer.starredRepositories` (stars, paginated), `viewer.repositories(affiliations:[OWNER])` (forks), `viewer.following`, `viewer.lists` (`UserListConnection`: id, name, slug, description, isPrivate, items).
- Write: `createUserList`, `updateUserList`, `deleteUserList`, `updateUserListsForItem(itemId, listIds[])`, `removeStar(starrableId)` (unstarring the repo itself, per story 8 — distinct from list-membership mutations).
- Load-bearing detail: `updateUserListsForItem` replaces a Star's *entire* list membership per call — it is not additive. The sync engine must always compute and send the complete desired `listIds` set per Star, never a delta.

**Sync/merge algorithm**

Three-way merge per Star, per sync: base (last-synced snapshot) vs. current GitHub state vs. pending local edits.
- Only one side changed since base → apply it.
- Both sides changed to the same result → no-op.
- Both sides changed to different results → GitHub wins; the local pending edit is written to the Retriage Queue, never applied, never silently dropped. No auto-merge/union.

**Naming convention & validation**

`{Intent}: {Category}` for Explore/Current/Retired/Reference; freeform for General. `Explore`/`Current`/`Retired` are mutually exclusive per Category. Validation flags non-conforming existing List names (e.g. the account's current unprefixed "Vendored skills" list) as needing a rename rather than silently guessing an Intent for them.

**State/config layout** (see ADR 0002)

- `~/.ghstars/config/` — taxonomy definitions, export mappings. Plain TOML/YAML files, user- or dotfiles-managed. Never auto-committed by ghstars.
- `~/.ghstars/state/` — local snapshot, Retriage Queue. ghstars never runs `git init` and never auto-commits; if the user already git-tracks this directory, `ghstars diff` can use its history, but committing is left entirely to the user.
- `~/.ghstars/runtime/` — ephemeral: caches, nudge files under `runtime/nudges/<theme>.md`, one file per theme, entries deduplicated by stable slug.

**Diff support**

`ghstars diff` wraps `git diff`/`git log -p` against `state/`'s repo when the user has git-tracked it themselves; a clear "no git history available" message otherwise. ghstars never commits on its own. No bespoke diff engine.

**CLI conventions**

Global `--json` flag; `--fields` selector on list-returning commands; no interactive prompts under `--json` (missing required input is a hard error with non-zero exit); `ghstars status --json` as the single health-check entrypoint (last sync time, Retriage Queue count, `Explore: General` count, verify pass/fail).

**Export engine**

Generic, config-driven: List/Category → output file → format. No hardcoded exporters; `tools.yaml`/`tools-under-exploration.yaml`-shaped mappings ship as example config, not special-cased code paths.

**Concurrency**

A local lockfile guards `state/` writes so concurrent invocations (human + agent, or multiple agent sessions) never race on the same files.

**Distribution**

PyPI + GitHub Releases with per-platform tar.gz binaries from v1; `uv tool install` supported. Designed to accommodate future `pipx`/`uvx`/`mise`/`eget` install paths, not built for them now.

## Testing Decisions

**Seam:** `ghstars.core`'s public functions/classes are the only thing tests call directly — never through the CLI subprocess or TUI rendering (confirmed with the user).

**Substituted dependency:** the GitHub client is the one fake — tests inject an in-memory implementation of the same interface `ghstars.github`'s real client implements (fetch stars/lists, create/update/delete list, update list membership for item). No real network calls, no `gh` CLI invocation in tests.

**Not mocked:** local `state/`/`config/` filesystem — tests use real temporary directories. File I/O is fast and deterministic enough that mocking it would hide bugs rather than prevent them.

**What makes a good test here:** assert on external behavior only — the returned Star/List records, Intent/Category assignments, Retriage Queue contents, `state/`'s git commits when present. Never assert on `ghstars.core`'s internal data structures. A good test survives a valid internal refactor and fails only when actual sync/conflict/taxonomy behavior changes.

**Modules to test:** the sync/merge engine (all four conflict scenarios: local-only change, remote-only change, both-same, both-different), taxonomy validation (name parsing, Intent/Category extraction, malformed-name detection), the export engine (mapping → output file content), Retriage Queue mechanics, nudge dedup logic.

**Prior art:** none in this repo (greenfield). The closest precedent is the old `gh-stars.py`'s `verify()` function — a deterministic, offline structural-check pattern worth mirroring for `ghstars`' own verification tests.

## Out of Scope

- Local checkout-mapping (detecting/managing locally cloned copies of starred repos under `~/repos`, `~/work`) — deferred, use case still unclear.
- Notes/journal integration and any feedback-loop tooling around explored tools — owned by the separate notes system; ghstars is a data/export provider only.
- Auto-committing `config/` to git — explicitly rejected, to avoid nested-repo conflicts with a stowed dotfiles repo.
- Any form of automatic `git init` — explicitly rejected; git support for `state/` is opt-in only.
- `pipx`/`uvx`/`mise`/`eget` packaging implementation — designed for, not built, in this spec.
- Nudge auto-application — nudges are observational only and never self-modify config.
- Import/migration from the old `905.github/stars/stars.json` — out of scope entirely for v1; ghstars starts from a fresh GitHub fetch, no local-file import path.
- Auto-committing `state/` — explicitly rejected; committing state/'s git history (when the user tracks it) is the user's responsibility, not ghstars'.
- TUI visual/interaction design details beyond "supports tagging, bulk tagging, retagging" — left to implementation/prototyping.
- Retriage Queue auto-resolution — always requires manual review; no auto-merge/union logic.

## Further Notes

- ADR 0001 (GitHub is the sole source of truth for List membership) and ADR 0002 (single `~/.ghstars/` directory instead of XDG base dirs) are binding architectural context — read both before implementing the sync engine or state layout.
- `updateUserListsForItem`'s full-replace semantics (confirmed via live GraphQL schema introspection and a live query against the user's own account, which returned 6 real Lists) is a load-bearing API detail, not an assumption.
- The old `gh-stars.py` script and `github-stars` skill stay in place until ghstars is verified stable; retirement is a follow-up action, not part of this build.
- The accompanying agent skill is a real deliverable of this effort, not a stretch goal. Its exact content is expected to firm up alongside `ghstars.cli`'s surface during implementation, following the same deterministic/agentic division of labor documented in the existing `github-stars` skill.
