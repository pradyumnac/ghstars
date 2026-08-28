# CLI reference

The stable, deterministic interface ticket 30 built for an agentic caller
(a future ticket 14 skill, or any other script). Every command documented
here calls `ghstars.core` for its logic; the CLI layer only parses
arguments, calls core, and renders the result. If a future agent skill
needs discovery, sorting, search, or a bulk mutation, it calls these
commands — it must never reimplement that logic itself (Scope 7).

This document is the authoritative reference for the agent contract:
every stable command, option, field set, JSON schema, machine error code,
exit code, and partial-failure rule. Where this document and a command's
own `--help` text disagree, this document wins; file a fix.

There is no schema version (Decision 9/18). A field-set or command-name
change and the ticket-14 skill change that depends on it must land in the
same change (see `CONTEXT.md`, "CLI field-set stability").

## Environment

`GHSTARS_HOME` overrides `~/.ghstars/`, the root for both state and
config. Unset, it defaults to `~/.ghstars/`. Set it to an isolated
directory for a live-account test or an agent sandbox run (Decision 10).

## Global conventions

- **`--json`** on any command restricts standard out to exactly one JSON
  document holding machine data. All human status text — progress,
  spinners, warnings — goes to standard error, or does not print. Parse
  standard out only; never scrape standard error.
- **Reads never mutate, and are offline unless documented otherwise.**
  `status` never creates a `GitHubClient`. `ratelimit` makes exactly one
  network call and never runs a sync.
- **A mutation always names its target explicitly.** No command accepts a
  Filter, a search term, standard input, or a wildcard as a mutation
  target (Scope 4). A Filter can discover names for a human to pass in;
  it can never select what gets changed.
- **Exit codes** (Decision 15; Typer's own usage-error code 2 is
  reserved and never raised by ghstars itself):

  | Code | Meaning |
  | --- | --- |
  | `0` | Success (or, for a bulk call, every target succeeded). |
  | `1` (`EXIT_TERMINAL`) | Failure will not resolve on retry. |
  | `2` | Typer usage error (bad arguments). |
  | `3` (`EXIT_RETRYABLE`) | Failure might resolve on retry. |
  | `4` (`EXIT_PARTIAL`) | Bulk call: some targets succeeded, some failed. |

  `diff` is the one exception — it returns git's own exit code verbatim
  (always `0`, whether or not there were changes); see its section below.

## Error contract

Every command that can fail routes through `ghstars.cli.errors.fail()`
(ADR 0010, status `proposed` — implemented exactly as the ADR specifies,
not yet formally accepted; Scope 0's live-account review is the
acceptance gate).

Under `--json`, a failure writes one JSON object to standard error:

```json
{"error": {"code": "no_local_record", "message": "...", "target": "a/b"}}
```

`target` is present only when the failure names a specific thing (a repo
full name, a Category name). Without `--json`, the same failure prints
`error: <message>` to standard error instead.

The exit code is `EXIT_RETRYABLE` (3) when `code` is one of
`rate_limit_exceeded`, `state_lock_held`, `network_failure`; every other
code exits `EXIT_TERMINAL` (1). This split holds whether or not the
caller passed `--json`.

Machine codes:

| Code | Retryable | Meaning |
| --- | --- | --- |
| `no_local_record` | no | No local Star record for the named target. Run `sync`. |
| `star_archived` | no | Target Star is Archived (unstarred) locally. |
| `list_membership_drift` | no | GitHub's live List membership for the target has diverged from local state since the last sync. |
| `tag_push_failed` | no | The List mutation itself failed on GitHub's side. |
| `rate_limit_exceeded` | yes | GitHub API rate limit hit before the call could complete. |
| `state_lock_held` | yes | Another `ghstars` process holds the local state lock. |
| `network_failure` | yes | A GitHub API call failed for a network/transport reason. |
| `invalid_input` | no | Bad argument value that Typer's own usage-error path doesn't catch (e.g. an unknown `--sort` mode, a missing `--yes`). |
| `unknown_field` | no | `--fields` named a field that doesn't exist on the record type. |
| `tool_unavailable` | no | A required external tool (`git`) is missing or `state/` isn't git-tracked. |

## Output contract

Two field sets exist per record type: **basic** (the default) and
**detailed** (`--details`). JSON mode and text mode return the same
fields for the same set — only the format differs. `--fields
a,b,c` overrides both named sets with an arbitrary, caller-ordered
subset, and works identically under `--json` and in text mode.

Basic-set text output is an aligned table. `--details` text output is a
key-value block per record, one blank line between records — a
detailed record is too wide for a table.

A list-returning command emits, under `--json`, one envelope shape
(Decision 19):

```json
{"total": 137, "offset": 0, "limit": 50, "rows": [...]}
```

`total` is the caller's own count of matching records before any page
was sliced off. Only `stars` is paged (`--limit`/`--offset`); `github-lists`
and `retriage` are bounded and unpaged, so they report `total =
len(rows)`, `offset = 0`, `limit = null`.

Paging is deterministic only while local state is unchanged. A `sync`
between two paged `stars` calls can insert or remove rows ahead of a
later `--offset` and shift it (Decision 21) — page through one static
snapshot, and re-run from `--offset 0` after a `sync`.

### Field sets

| Record | Basic | Detailed |
| --- | --- | --- |
| Star row (`stars`) | `full_name`, `list_names`, `starred_at`, `stargazer_count` | every `Star` field (`full_name`, `html_url`, `description`, `starred_at`, `first_seen`, `language`, `license`, `stargazer_count`, `fork`, `follow`, `archived`, `archived_at`, `last_checked`, `list_ids`, `pending_list_ids`) plus `list_names` |
| List (`github-lists`) | `name`, `intent`, `category`, `is_private`, `malformed` | every `List` field (`id`, `name`, `slug`, `description`, `is_private`, `intent`, `category`, `malformed`, `items`) |
| Retriage entry (`retriage`) | `star_full_name`, `attempted_list_ids`, `conflict_detected_at`, `resolved` | every `RetriageEntry` field (same four — the whole record is small) |
| Export row (`export`, config-driven, not `--fields`-selectable at the CLI) | `full_name`, `html_url`, `description` | every `Star` field |

`archived` appears in `stars`' output only when the caller passes
`--include-archived` (Decision 22) — without the field, an Archived Star
and an active Star render identically, and an agent could try to `tag` an
Archived Star and hit `star_archived` with no clue why.

## Commands

### `ghstars stars`

Query locally synced Stars: every Filter, search, and sort in
`core.discovery` (Scope 1), through the same query the TUI uses. The CLI
implements none of that logic itself.

Named `stars`, not `list` — see "Command names", below.

| Option | Repeatable | Meaning |
| --- | --- | --- |
| `--category NAME` | yes | Star belongs to a List in this Category. |
| `--intent NAME` | yes | Star belongs to a List with this Intent. |
| `--list LIST_ID` | yes | Star belongs to this exact List id. |
| `--language NAME` | yes | Primary language matches exactly. |
| `--license NAME` | yes | License matches exactly. |
| `--owner NAME` | yes | Owner (the part of `full_name` before `/`) matches. |
| `--fork` | — | Only forks. |
| `--followed` | — | Only Stars whose owner is followed. |
| `--unclassified` | — | Only Stars belonging to no List. |
| `--recent WINDOW` | — | `1d`, `1w`, `1m`, `3m`, `1y`, or `older_1y`. |
| `--search TEXT` | — | Case-insensitive substring match on name/description. |
| `--sort MODE` | — | One of the 12 modes below. Default `starred_desc`. |
| `--include-archived` | — | Include Archived Stars (excluded by default). |
| `--limit N` | — | Max rows to return. Default 50. |
| `--offset N` | — | Skip this many matching rows before `--limit`. |
| `--details` | — | Detailed field set instead of basic. |
| `--fields a,b,c` | — | Explicit field subset; overrides `--details`. |
| `--json` | — | Emit the list envelope. |

All Filter options combine with AND (Decision 12). Sort modes:
`name_asc`, `name_desc`, `starred_asc`, `starred_desc`, `stargazer_asc`,
`stargazer_desc`, `language_asc`, `language_desc`, `list_count_asc`,
`list_count_desc`, `list_name_asc`, `list_name_desc`. An unrecognized
`--sort` value fails with `invalid_input` rather than silently falling
back to the default.

Exit codes: `0` on success, `invalid_input` → `EXIT_TERMINAL` (1) for an
unknown `--sort` value.

### `ghstars github-lists`

Locally synced GitHub Lists, with parsed Intent/Category. Bounded output
— no `--limit`, no `--offset` (Decision 20).

Named `github-lists`, not `lists` — see "Command names", below.

| Option | Meaning |
| --- | --- |
| `--details` | Detailed field set instead of basic. |
| `--fields a,b,c` | Explicit field subset; overrides `--details`. |
| `--json` | Emit the list envelope. |

### `ghstars facets`

Every value an agent can pass to `stars`' Filter options, read from the
caller's own synced data (Decision 25) — the way to discover what a
Filter accepts without guessing.

| Option | Meaning |
| --- | --- |
| `--json` | Emit one object with all six facet groups. |

`--json` shape:

```json
{
  "categories": ["Tools", "..."],
  "intents": ["Explore", "Current", "Retired"],
  "lists": [{"id": "...", "name": "...", "...": "..."}],
  "languages": ["Python", "..."],
  "licenses": ["MIT", "..."],
  "owners": ["octocat", "..."]
}
```

`lists` holds full dumped `List` records (not just names), so a caller
gets both `id` (to pass to `stars --list`) and `name` in one call.

### `ghstars retriage`

Stars whose staged List-membership edit conflicted with a concurrent
GitHub-side change at the last sync (GitHub always wins that conflict,
ADR 0001). Local-only, never synced to GitHub. Bounded output — no
`--limit`, no `--offset` (Decision 20).

| Option | Meaning |
| --- | --- |
| `--details` | Detailed field set instead of basic. |
| `--fields a,b,c` | Explicit field subset; overrides `--details`. |
| `--json` | Emit the list envelope. |

### `ghstars tag REPO LIST_NAME`

Add one or more repos to a List and push the change to GitHub
immediately. A new List is created for real if `LIST_NAME` doesn't exist
yet.

| Option | Repeatable | Meaning |
| --- | --- | --- |
| `--repo NAME` | yes | Additional repo to tag into the same List (bulk). |
| `--private` | — | Create the List private if new (default public). |
| `--json` | — | Emit JSON. |

**Single target** (no `--repo`): fails the whole call on any error, with
a specific machine code (`no_local_record`, `star_archived`,
`list_membership_drift`, `tag_push_failed`, `network_failure`,
`state_lock_held`). `--json` success shape:

```json
{"full_name": "a/b", "list_ids": [...], "removed_list_ids": [...]}
```

**Bulk** (one or more `--repo`): isolates each target's failure from the
rest. `--json` shape:

```json
{
  "targets": ["a/b", "c/d"],
  "results": [
    {"full_name": "a/b", "tagged": true, "list_ids": [...], "removed_list_ids": [...], "error": null},
    {"full_name": "c/d", "tagged": false, "list_ids": null, "removed_list_ids": null, "error": "..."}
  ]
}
```

Exit codes: `0` if every target succeeded, `EXIT_PARTIAL` (4) if some
did and some didn't, `EXIT_TERMINAL` (1) if none did.

### `ghstars unstar REPO`

Unstar one or more repos on GitHub for real, then mark their local
record Archived (never deleted). A real, visible mutation.

| Option | Repeatable | Meaning |
| --- | --- | --- |
| `--repo NAME` | yes | Additional repo to unstar in the same call (bulk). |
| `--yes` | — | Confirm. Required, single or bulk (Decision 1). |
| `--json` | — | Emit JSON. |

Every unstar — single or bulk — requires `--yes`. There is no
interactive prompt at all: a terminal-gated prompt would not work for a
non-interactive caller, so `--yes` is the whole confirmation contract.
Without it, the command fails with `invalid_input` before mutating
anything, and the failure message lists every target that would have
been unstarred. Only explicit repository names can select a target — no
Filter, search term, standard input, or wildcard.

For more than one target, the command also prints `Targets: a/b, c/d`
(stdout in text mode, stderr under `--json`) before mutating anything.

**Single target** `--json` success shape:

```json
{"full_name": "a/b", "unstarred": true, "archived_locally": true}
```

**Bulk** `--json` shape:

```json
{
  "targets": ["a/b", "c/d"],
  "results": [
    {"full_name": "a/b", "unstarred": true, "archived_locally": true, "error": null},
    {"full_name": "c/d", "unstarred": false, "archived_locally": null, "error": "..."}
  ]
}
```

Exit codes: same rule as `tag` — `0` / `EXIT_PARTIAL` (4) /
`EXIT_TERMINAL` (1) for the bulk path; single-target failures use the
`fail()` machine code's own retryable/terminal split.

### `ghstars category rename OLD NEW`

Rename a Category across its Explore/Current/Retired Lists, consistently,
in one operation. Fetches fresh GitHub state right before writing and
skips (reports, never overwrites) any List whose live state has already
diverged since the last sync.

| Option | Meaning |
| --- | --- |
| `--json` | Emit JSON. |

`--json` shape: `{"renamed": [...], "skipped": [...]}` (List ids).
Failure codes: `invalid_input` (bad name), `no_local_record` (no
Explore/Current/Retired List found for `OLD`), `network_failure`,
`state_lock_held`.

### `ghstars category drain FROM TO`

Bulk-migrate every Star from one Category into another, preserving each
Star's lifecycle Intent (Explore stays Explore, etc). Same live-state
divergence check as `rename`.

| Option | Meaning |
| --- | --- |
| `--private` | Create any destination List private if new (default public). |
| `--json` | Emit JSON. |

`--json` shape: `{"migrated": [...], "skipped": [...]}` (Star full
names). Same failure codes as `category rename`.

### `ghstars status`

Local-state health in one call. Reads only `StateStore.load_*()` — never
creates a `GitHubClient`, never makes a network call — so an agent can
call this before deciding whether a `sync` round trip is even worth it.

| Option | Meaning |
| --- | --- |
| `--json` | Emit JSON. |

`--json` shape:

```json
{
  "last_sync_at": "2026-08-28T00:00:00+00:00",
  "active_star_count": 0,
  "archived_star_count": 0,
  "list_count": 0,
  "unclassified_count": 0,
  "pending_edit_count": 0,
  "retriage_queue_count": 0,
  "verify_ok": true,
  "verify_problems": []
}
```

`pending_edit_count` counts Stars whose `pending_list_ids` is not null;
it stays zero while ADR 0004 keeps pending staging dormant. `verify_ok`
is a deterministic, offline structural check (duplicate ids, dangling
List references); `verify_problems` lists each one when `verify_ok` is
`false`.

### `ghstars ratelimit`

The live GitHub API rate limit — a separate, explicit network call, never
folded into `status`. Makes exactly the one `check_rate_limit()` call
`sync` itself makes before fetching anything; never runs a full sync.

| Option | Meaning |
| --- | --- |
| `--json` | Emit JSON. |

`--json` shape: `{"remaining": 4999, "limit": 5000, "ok": true}`.

### `ghstars sync`

Fetch Stars and Lists from GitHub into local state.

| Option | Meaning |
| --- | --- |
| `--debug` | Verbose fetcher logging to stderr (also honors `GHSTARS_DEBUG=1`). |
| `--json` | Emit JSON. |

`--json` shape — the ordered stage labels plus the final result in one
document:

```json
{
  "stages": ["Fetching stars...", "Fetching lists...", "..."],
  "star_count": 1550,
  "list_count": 42,
  "failed_tag_pushes": []
}
```

Human progress (spinner, or `--debug`'s stage lines) always goes to
standard error, so it never corrupts the `--json` document on standard
out. Failure codes: `rate_limit_exceeded`, `network_failure`,
`state_lock_held`.

### `ghstars export`

Write local Stars out to file(s), per the `[export]` table of
`~/.ghstars/config/ghstars.toml` (or `$GHSTARS_HOME/config/ghstars.toml`).
Generic and config-driven — see `docs/how-to/export.md` for the config
format; there is no CLI flag to select what gets exported.

| Option | Meaning |
| --- | --- |
| `--json` | Emit JSON. |

`--json` shape: an array of per-export results,
`{"name", "star_count", "output", "format", "skipped_malformed_lists"}`.
An empty `[export]` table emits `[]`, not an error.

### `ghstars diff [ARGS...]`

Show classification changes in `state/`, via the user's own git history.
This only works if the user has git-tracked `state/` themselves (ghstars
never runs `git init` or commits there — ADR 0002); a bespoke diff engine
was rejected. This shells out to the user's own `git` and shows its
output verbatim.

| Option | Meaning |
| --- | --- |
| `--patch` | Full `git diff` patch instead of the default `git diff --stat` summary. |
| `--log` | `git log -p` (commit history) instead of the working-tree diff. |
| `ARGS...` | Passed through verbatim to `git`, e.g. a revision or path. |

**The agent contract is the zero-argument form only**: run `ghstars
diff` with no arguments, and detect a change by non-empty output — never
by exit code. Argument pass-through (`--patch`, `--log`, revisions,
paths) exists for a human caller and is explicitly outside the agent
contract (Decision 11).

Exit code: **git's own, verbatim** — this is the one command that does
not follow the `0`/`1`/`3`/`4` table above. `git diff`/`git diff --stat`
exit `0` whether or not anything changed, so the exit code here never
says whether anything changed; only the output does. A missing/broken
git binary or an untracked `state/` fails with `tool_unavailable` or
`invalid_input` instead of running git at all.

### `ghstars tui`

Launch the interactive TUI. Interactive only — not part of the agent
contract, has no `--json`, and is out of scope for this document.

## Command names

Flagged 2026-08-28: `list` (Stars, filtered/paged) and `lists` (GitHub
Lists, bounded) read as a typo of one command, not two distinct nouns —
ambiguous for a human or an agent parsing a bare command name out of
context. Scope 7 reviewed the full command-name set in one pass, per the
ticket's own instruction not to rename piecemeal (a rename after ticket
14's skill exists doubles the surface that has to move in lockstep).

**Resolution (Decision 26): both renamed, not just one.**

- `list` → **`stars`** — Stars are the tool's own primary entity
  (`ghstars` = GitHub *Stars*); the noun names what the row is, with no
  implicit contrast against anything else.
- `lists` → **`github-lists`** — explicit that this is GitHub's List
  feature, not a second sense of "Stars, listed." Kept the domain word
  "List" (it is the established term throughout `CONTEXT.md` and the
  core model), prefixed for the disambiguation the flat command
  inventory needs.

Both names are now fully self-describing on their own — an agent (or a
human) reading `ghstars --help`'s command list does not need the other
command's name for contrast, which a `list`/`lists` pair required.

**What this did *not* touch**, and why each is safe to leave alone:

- The `--list` Filter option on `stars` (`--list LIST_ID`). It names the
  domain entity being filtered on, the same way `--category`/`--intent`
  do; it was never a command name, and nothing reads it out of context
  the way a bare top-level command name is.
- `FIELD_REGISTRY["list"]` (in `core/fields.py`) and the `List` model
  itself. Same reasoning — a registry key and a class name, not a
  command surface.
- `list_names` (the resolved-List-names field on a Star row) and
  `payload["lists"]` (the facet group key in `ghstars facets --json`).
  Both are field/key names describing List data, not command names.
- `category rename` / `category drain` vs. the top-level commands. No
  clash: `category` is a distinct subcommand group, and `rename`/`drain`
  read unambiguously as verbs on a Category, not as competitors to
  `stars`, `github-lists`, `retriage`, or `facets`.

Every other command name (`sync`, `tag`, `unstar`, `status`, `ratelimit`,
`export`, `diff`, `tui`) is a single unambiguous word with nothing
adjacent to clash against.

## What this document does not cover

Per ticket 30's non-goals: TUI layouts, colours, keybindings, view state,
the config editor, opening a repository in a browser, and Folder/grid
presentation are not part of the CLI and are not documented here.
