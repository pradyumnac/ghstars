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
4. As a developer, I want unclassified new stars to be visible as Unclassified rather than slip through unnoticed, so that I always know what still needs a decision — without ghstars writing anything to my real GitHub Lists on my behalf (superseded by ADR 0007: never pushed to `Explore: General` or anywhere else; "Unclassified" is a derived local view, `ghstars status`'s `unclassified_count`).
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

 1. As a developer, I want to classify a Star using `Explore`, `Current`, `Retired`, or `Reference` Intent prefixes on List names, so that the List name itself fully encodes my relationship to that Category.
 2. As a developer, I want `Explore`, `Current`, and `Retired` to be mutually exclusive per Category, so that a Star's adoption status for a given Category is always unambiguous.
 3. As a developer, I want to move a Star from `Current` to `Retired` without unstarring it, so that I can keep a record of things I used to rely on without cluttering my active tool lists.
 4. As a developer, I want `Reference` Lists to have no adoption lifecycle, so that informational collections (e.g. "Reference: AI Agents") aren't forced into a Current/Explore choice that doesn't apply.
 5. As a developer, I want General Lists with no Intent prefix, so that Lists outside the tool-adoption domain aren't forced into this taxonomy.
 6. As a developer, I want to add new Categories on demand, so that my taxonomy can grow as my interests do.
 7. As a developer, I want to rename a Category and have all its Lists (across Intents) renamed consistently, so that I don't have to manually update Current/Explore/Retired variants separately.
 8. As a developer, I want to "drain" (bulk-migrate) all Stars from one Category into another, so that I can reorganize my taxonomy without manually moving each Star.
 9. As a developer, I want ghstars to validate that List names conform to the `{Intent}: {Category}` convention (or are recognized as General), so that a malformed name doesn't silently break sync or export.

### TUI

 1. As a developer, I want a TUI for fast interactive tagging, so that I can quickly triage a batch of unclassified stars without leaving the terminal.
 2. As a developer, I want bulk tagging in the TUI, so that reclassifying many repos at once doesn't require repetitive single-item actions.
 3. As a developer, I want retagging support in the TUI, so that I can move a Star between Categories or Intents as my usage of it evolves.
 4. As a developer, I want the TUI to show each List's public/private status explicitly, so that I never mistake a private List for a public one or vice versa.

### CLI & agent integration

 1. As an agent driving ghstars via scripts, I want a `--json` flag on every subcommand, so that I get structured, parseable output instead of scraping human-formatted text.
 2. As an agent, I want a `--fields` selector on list-returning commands, so that I only pay the token cost for the fields I actually need.
 3. As an agent, I want agent-mode output to never include interactive prompts, so that a missing required decision fails hard with a clear error instead of hanging.
 4. As an agent, I want a single `ghstars status --json` command reporting last sync time, Retriage Queue count, and unclassified-star count, so that I can decide what to do next without pulling full records.
 5. As an agent, I want write operations to be idempotent where feasible, so that retrying a call after a timeout doesn't manufacture a spurious conflict against my own prior attempt.
 6. As a developer running concurrent ghstars invocations (human + agent, or two agent sessions), I want a local lockfile around state writes, so that concurrent operations never corrupt local state.

### Export

 1. As a developer, I want to define a generic mapping from a List (or Category) to an output file and format, so that I can drive my own downstream pipelines (`tools.yaml`, skill vendor lists) without ghstars hardcoding my specific use cases.
 2. As a developer, I want to ask "what tools am I currently exploring but haven't tried yet," so that I have an easy on-ramp into repos I starred but never followed up on.

### State & diffing

 1. As a developer, I want ghstars to never auto-commit `state/`, so that I retain full control over when history is recorded — even when `state/` is already a git repo, committing stays my responsibility, not ghstars'.
 2. As a developer, I want ghstars to never run `git init` on its own, so that git-tracking `state/` is something I opt into deliberately, not an unrequested side effect.
 3. As a developer, I want a `ghstars diff` command, so that I (or an agent) can see exactly what changed in my classification since the last sync.
 4. As a developer, I want `config/` to stay plain files, never auto-committed by ghstars, so that stowing it into my dotfiles repo doesn't create a nested-repo conflict.

### Nudges

 1. As a developer, I want the accompanying agent skill to record "nudges" — observations about workflow friction — without acting on them, so that I retain full control over whether to actually change my config or workflow.
 2. As a developer, I want nudges deduplicated by a stable key, so that repeated friction doesn't spam me with duplicate notes.
 3. As a developer, I want nudge surfacing off by default, so that this feature doesn't clutter normal usage until I've opted in.
 4. As a developer, I want nudges to never appear in `--json`/agent-mode output, so that they don't undercut the token-efficiency the CLI's agent mode is meant to provide.
 5. As an agent, I want to only read the nudge files when I have something new to record, so that normal operation doesn't pay the token cost of loading nudge state on every call.

### Distribution & retirement

 1. As a developer, I want ghstars installable via `uv tool install`, PyPI, and GitHub Releases with per-platform tar.gz binaries, so that I have flexible install paths from day one.
 2. As a developer, I want an accompanying agent skill shipped alongside ghstars, mirroring the existing `github-stars` skill's structure, so that Claude and other agents know how to drive and monitor it correctly.
 3. As a developer, I want the old `gh-stars.py` script and `github-stars` skill retired once ghstars is stable, so that I'm not maintaining two overlapping GitHub-stars fetchers.

### Privacy

 1. As a developer, I want new Lists to default to public, matching my existing Lists, with an explicit `isPrivate` override available per List, so that I can keep sensitive groupings private without changing my established default.

### TUI (addendum)

 1. As a developer, I want the TUI to show my remaining GitHub API rate limit, so that I can tell when I'm approaching a sync-blocking limit before it happens. Numbered out of sequence with the rest of the TUI section (24-27) to avoid renumbering every other story's cross-references elsewhere in this doc and the codebase.

### TUI: navigation, presentation, and configuration

Stories 50-72 replace the earlier "TUI visual/interaction design left to
implementation" deferral. Story numbers continue from 49 for the same
cross-reference reason.

**Navigation**

 1. As a developer, I want to switch View Mode between a flat Star list, a grid, and a Folder, so that I can pick the arrangement that suits the job in front of me.
 2. As a developer, I want Folder mode to show my Lists as containers and open one List into its Stars, so that I can work through one List at a time.
 3. As a developer, I want a Star that belongs to no List to appear in one default Folder, so that unclassified Stars stay reachable and never disappear from the TUI.
 4. As a developer, I want grid mode to show each Star as a card with the description cut to a fixed character count, so that cards stay the same size and the grid stays readable.

**Finding Stars**

 1. As a developer, I want to filter the Stars on screen by Category, Intent, List, Language, License, Owner, Fork, Follow, and repository metadata, so that I can narrow a large account to the set I care about.
 2. As a developer, I want a Filter to work inside Folder mode as well as the flat modes, so that the container I am in and the Filter I applied stay independent.
 3. As a developer, I want to search Stars by name and description as I type, so that I can reach one repo out of 1530 without scrolling. Search composes with every Filter.
 4. As a developer, I want a Filter for unclassified Stars only, so that I have a direct triage queue.
 5. As a developer, I want to sort by name, star date, stargazer count, language, List count, and List name, and to reverse any of them, so that I can order the view for the task at hand. Star date descending is the default, because the newest Stars are the ones that need classification.

**Finding Stars filter design:**

- Press `f` to open one Filter menu. From that menu, press `c` for Category,
  `i` for Intent, `l` for List, `g` for Language, `v` for License, `r` for
  Recency, `o` for Owner, `k` for Forks, `w` for Followed, `u` for
  Unclassified, and `x` to clear the active Filter. The menu exposes every
  action for discovery.
- Filter by `starred_at` recency with these ranges: 1 day, 1 week, 1 month,
  3 months, 1 year, and older than 1 year. Use the current time as the
  reference, not the last sync time. In the Recency picker, use `d`, `w`,
  `m`, `3`, `y`, and `o` for these ranges.
- Offer local metadata filters for Forks, Followed owners, and Owner. The
  default active-Star view excludes Archived Stars, so Archived is not an
  active filter until a view includes archived records.
- Filter by License using the value fetched into the Star record.
- Search and Filter apply together. A Filter first narrows the candidate
  Stars; Search then matches the repository name and description within that
  result. Escape clears Search. Enter keeps Search active and returns focus
  to the Star table.

 1. As a developer, I want a detail pane for the Star under the cursor, showing every field the last sync stored, so that I can judge a repo without opening a browser.

**Presentation**

 1. As a developer, I want List and Category names shown in colour, so that I can tell groups apart at a glance. ghstars derives the colour from the Category name, and ships soft pastel defaults.
 2. As a developer, I want to set the colour palette in config, so that the colours suit my terminal theme. The palette must stay readable on a light and a dark background.
 3. As a developer, I want to set header height, row height, and whether the clock shows, so that I can trade screen density against readability.
 4. As a developer, I want a top bar showing remaining API rate limit, last sync time, and List count, so that I can see account state without leaving the TUI.
 5. As a developer, I want a bottom status bar showing the visible and total Star count, the pending-edit count, the active sort, and the active Filter, so that I always know what the view is showing me. The sort and the Filter appear last, each with its key, for example `sort: newest [s]`.

**Actions**

 1. As a developer, I want the `y` key to start a full sync from inside the TUI, so that I can refresh stale data where I noticed it was stale. ghstars only syncs when I press the key (see ADR 0006). The TUI shows each sync stage, completion, and errors. It never starts sync automatically.
 2. As a developer, I want a separate, short-named key that refreshes the API rate limit alone, so that a cheap check stays distinct from a full sync.
 3. As a developer, I want to open the Star under the cursor in my browser, so that I can read the repo itself. ghstars uses the XDG default handler.
 4. As a developer, I want to unstar the Star under the cursor after I confirm in a dialog, so that a real, irreversible GitHub change can never happen from one keypress.

**Configuration**

 1. As a developer, I want to set every keybinding in config, so that the TUI matches the keys I already use.
 2. As a developer, I want to edit config from inside the TUI and save it deliberately, so that I do not have to leave the TUI to change a setting.
 3. As a developer, I want ghstars to remember my last View Mode, sort, Filter, and Detail pane visibility between sessions, so that the TUI opens where I left it.

**Responsiveness**

 1. As a developer, I want the TUI to draw immediately on launch and never block on a network call, so that a slow GitHub response never looks like a hang. Every panel that waits on data shows a labelled placeholder first.

## Implementation Decisions

**Modules**

- `ghstars.core` — the single test seam. Pydantic data models, the sync engine (fetch/merge/conflict/push), taxonomy validation, the export engine, an abstract GitHub client interface, the local state store, the Retriage Queue, and the nudge store.
- `ghstars.github` — the concrete GitHub API client, implementing `ghstars.core`'s abstract client interface over `gh api graphql`.
- `ghstars.cli` — Typer CLI, a thin wrapper over `ghstars.core`. Owns `--json`/`--fields`/agent-mode conventions.
- `ghstars.tui` — Textual TUI, a thin wrapper over `ghstars.core`.
- Accompanying agent skill (separate deliverable, vendored the same way `github-stars` is today) — documents the deterministic/agentic division of labor below for agents driving `ghstars.cli`.

**Data model (Pydantic)**

- `Star`: full_name, html_url, description, starred_at, first_seen, language, license, stargazer_count, fork, follow, archived, archived_at, last_checked, list memberships.
- `List`: id (GitHub node ID), name, slug, description, is_private, intent (`Explore`/`Current`/`Retired`/`Reference`/`None` for General), category, items.
- `RetriageEntry`: star full_name, attempted list change, conflict detected at, resolved (bool).
- `Nudge`: stable slug/key, theme, message, count, last_seen.
- No separate sync-log schema — `state/`'s git commits (when present) serve this role; no bespoke log format to design or maintain.

**GitHub API contract (GraphQL)**

- Read: `viewer.starredRepositories` (stars, paginated, including `licenseInfo`), `viewer.repositories(affiliations:[OWNER])` (forks), `viewer.following`, `viewer.lists` (`UserListConnection`: id, name, slug, description, isPrivate, items).
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

- `~/.ghstars/config/` — taxonomy definitions, export mappings, TUI settings (`tui.toml`: keybindings, colour palette, header height, row height). Plain TOML/YAML files, user- or dotfiles-managed. Never auto-committed by ghstars.
- `~/.ghstars/state/` — local snapshot, Retriage Queue, and TUI session state (`tui-state.toml`: last View Mode, sort, Filter, and Detail pane visibility). ghstars never runs `git init` and never auto-commits; if the user already git-tracks this directory, `ghstars diff` can use its history, but committing is left entirely to the user.

**TUI config: two files, split by who writes them** (story 69-71, ADR 0002)

`config/tui.toml` holds settings the user authors. ghstars reads it on
launch. ghstars writes it only when the user saves an edit from the TUI
(story 70), and uses a style-preserving TOML writer so user comments and
key order survive the write. `config/` is stow-managed dotfiles, so an
unasked-for rewrite would show up as churn in the user's dotfiles repo.

`state/tui-state.toml` holds session state ghstars writes on its own
(story 71). It lives under `state/`, which is already untracked, so
remembering a sort order never dirties a dotfiles repo.

A missing file means defaults, never an error — the same rule
`load_export_config` already follows for `export.toml`.

- `~/.ghstars/runtime/` — ephemeral: caches, nudge files under `runtime/nudges/<theme>.md`, one file per theme, entries deduplicated by stable slug.

**Diff support**

`ghstars diff` wraps `git diff`/`git log -p` against `state/`'s repo when the user has git-tracked it themselves; a clear "no git history available" message otherwise. ghstars never commits on its own. No bespoke diff engine.

**CLI conventions**

Global `--json` flag; `--fields` selector on list-returning commands; no interactive prompts under `--json` (missing required input is a hard error with non-zero exit); `ghstars status --json` as the single health-check entrypoint (last sync time, Retriage Queue count, Unclassified count, verify pass/fail).

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
- Retriage Queue auto-resolution — always requires manual review; no auto-merge/union logic.
- TUI pagination and page-size config — **postponed, not rejected**. Measured on the real 1530-Star account: `load_stars()` 32ms, building all 1530 `DataTable` rows 52ms, full rebuild 56ms, one `update_cell` 0.1ms. Textual's `DataTable` already virtualizes painting. Pagination would add config, state, and keys to solve 85ms. Revisit if a real account reaches a size where the measurement changes. Story 72 (non-blocking launch) is the part that must be built now.
- Compound Category, splitting a Category into a kind and a subject (for example `Explore: Dev Tools / AI`) — **deferred to a follow-up issue, ADR, and spec entry**. The direction is chosen, the mechanism is not. It changes `parse_list_name`, and it needs a migration path for existing List names. Stories 50-72 assume today's single freeform Category, and the Filter design (story 54) must leave room for a second axis later.
- Immediate push of a tag edit from the TUI — owned by ticket 16, not by these stories. `tag_star()` stages `pending_list_ids` today; the TUI renders that staged state honestly. Ticket 16 still has three unresolved design questions about narrowing the three-way merge to one Star.
- Filtering by GitHub's own repository topics — ghstars never fetches `repositoryTopics`, and the taxonomy lives in List names by design.

## Further Notes

- ADR 0001 (GitHub is the sole source of truth for List membership) and ADR 0002 (single `~/.ghstars/` directory instead of XDG base dirs) are binding architectural context — read both before implementing the sync engine or state layout.
- ADR 0006 (the TUI can sync on an explicit keypress) supersedes ADR 0003 and governs stories 65 and 66. Read it before adding any live GitHub call to the TUI.
- ADR 0005 (compound Category) is `proposed`, not accepted. Do not build against it.
- ADR 0007 supersedes story 4 as originally written: a never-classified Star is never pushed into `Explore: General` or any other List. "Unclassified" is a derived local view (`list_ids == [] and not archived`), never a real GitHub List membership ghstars writes on the user's behalf.
- The TUI's rate-limit worker catches only `GitHubApiError` (`tui/app.py:432`). A `ValidationError` from `RateLimitResponse.model_validate` escapes the worker and leaves the bar blank with no message. Story 63 must fix this, and match the broad-catch reasoning `_apply_tag` already documents.
- `updateUserListsForItem`'s full-replace semantics (confirmed via live GraphQL schema introspection and a live query against the user's own account, which returned 6 real Lists) is a load-bearing API detail, not an assumption.
- The old `gh-stars.py` script and `github-stars` skill stay in place until ghstars is verified stable; retirement is a follow-up action, not part of this build.
- The accompanying agent skill is a real deliverable of this effort, not a stretch goal. Its exact content is expected to firm up alongside `ghstars.cli`'s surface during implementation, following the same deterministic/agentic division of labor documented in the existing `github-stars` skill.
