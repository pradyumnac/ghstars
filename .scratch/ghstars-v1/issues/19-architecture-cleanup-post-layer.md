# 19 — Architecture cleanup from the 07/09/10/11 advisor review

**What to build:** five structural cleanups, all originating from the
2026-08-17 whole-project advisor review over the merged 07/09/10/11 layer
(see `HANDOFF.md`'s now-landed "Architecture-improvement suggestions"
section for full traceability — this ticket is the landing place, replacing
that section as the source of truth going forward). None of these change
user-facing behavior; all are report-only findings the user asked to be
addressed before ticket 08.

**Blocked by:** none (07, 09, 10, 11 are all done).

**Status:** done

## Scope 1 — Split `cli/__init__.py` into per-command modules

- [x] `src/ghstars/cli/__init__.py` (532 lines across ~10 commands) is
      split into `cli/commands/{sync,list_lists,tag,unstar,retriage,category,
      export,diff,tui}.py` (exact grouping left to the implementer — group
      by feature, not 1:1 per command, where commands are tightly related),
      each registering its command(s) on the shared `app`/`category_app`
      Typer instances.
- [x] `cli/__init__.py` itself shrinks to app/`category_app` construction,
      shared helpers used by multiple command modules (e.g.
      `_render_records`), and importing/registering the command modules —
      mirroring how `core/__init__.py` already re-exports from submodules.
- [x] No command's behavior, help text, or `--json`/`--fields` contract
      changes — this is a pure module reorganization, covered by the
      existing `test_cli.py`/`test_cli_diff.py`/etc. test suites passing
      unchanged.

## Scope 2 — Consolidate duplicated List-membership-mirroring logic

- [x] `sync.py::_apply_pushed_membership` and
      `category.py::_apply_membership_diff` are near-identical logic for
      mirroring a membership push onto `List.items` — `category.py`'s own
      docstring already admits it's a private copy rather than an import.
      Extract one shared helper (in `core/`, wherever fits best without
      creating an import cycle between `sync.py` and `category.py`) and have
      both call sites use it.
- [x] Existing `test_sync.py` and `test_category.py` coverage for both call
      sites passes unchanged against the shared helper.

## Scope 3 — Consolidate the "fetch fresh, skip diverged" pattern

- [x] `category.py`'s `rename_category()` and `drain_category()`
      independently implement "fetch fresh GitHub state, skip and report
      any item that diverged from the local snapshot that triggered this."
      Extract a shared "fetch-and-diff-against-local-snapshot" primitive
      that both call, so a future ticket-07-shaped command doesn't
      reimplement it a third time.
- [x] Existing `test_category.py` coverage for both commands' skip-diverged
      behavior passes unchanged against the shared primitive.

## Scope 4 — Mechanically enforce the no-auto-sync guarantee (ADR 0003)

- [x] Add a test that asserts `ghstars tui`'s bare launch (`on_mount`, no
      user interaction) makes zero calls through `GitHubClient`'s
      `_graphql()` chokepoint other than `check_rate_limit()` — turning
      [ADR 0003](../../../docs/adr/0003-github-sync-is-always-explicit.md)'s
      rule into something CI checks automatically, rather than relying on
      manual review each time a new layer merges.
- [x] The mechanism (a call-counting fake/spy around `_graphql()`, or
      equivalent) is left to the implementer, but must be reusable for a
      future ticket 14 (agent skill) test making the same assertion.

## Scope 5 — Reduce `tag_star()`'s redundant `fetch_lists()` cost

- [x] `tag_star()` (`core/tagging.py`) re-fetches Lists live on every call,
      by design (see its own docstring). Bulk-tagging N stars into the same
      List today costs N redundant `fetch_lists()` calls — already flagged
      as a deferred issue in `tui/app.py`'s `_apply_tag` docstring.
- [x] **Needs a design decision during implementation, not just guessed
      at**: the shape of the fix is open — e.g. `tag_star()` gaining an
      optional pre-fetched `lists` parameter that a caller doing a bulk
      operation (the TUI's bulk-tag action) can supply once instead of
      per-star. Whoever picks up this scope should propose the seam shape
      as a comment before implementing it, since it changes `tag_star()`'s
      signature and every existing call site.
- [x] Existing `test_tagging.py` and `test_tui.py` coverage for `tag_star()`
      and bulk-tagging passes unchanged (single-call-site callers keep
      working with no `lists` argument supplied).

## Comments (pre-implementation, from the advisor review, 2026-08-17)

Findings are quoted from the review report; see git history around commit
`554c236` (ADR 0003) and the HANDOFF.md diff that landed alongside it for
the original wording. All five scopes are independent of each other — no
ordering constraint between them, can be split across parallel worktree
agents the same way 07/09/10/11 were, or done serially in one pass; left to
whoever implements this ticket.

The user's instruction was explicit: this ticket should be done **before**
ticket 08 — see ticket 08's `Blocked by` line, updated to include this
ticket.

## Comments (implementation, done serially in one worktree agent pass)

All five scopes done in one pass (no ordering constraint between them, per
above); `mise run check` green, 198 tests (197 existing, unchanged
behavior, + 1 new for scope 4).

**Scope 1**: `cli/__init__.py` (532 lines) is now 97 lines — app/
`category_app` construction, `main()`'s callback, and `_render_records`
only. Ten commands landed in nine `cli/commands/*.py` modules exactly as
suggested (`category.py` holds both `rename`/`drain`). `cli/commands/
__init__.py` imports every submodule for its registration side effect,
imported itself from the bottom of `cli/__init__.py` — mirrors `core/
__init__.py`'s re-export pattern.

The one real wrinkle: `tests/test_cli.py`/`test_cli_diff.py` monkeypatch
`get_client`/`get_store`/`ensure_config_dir`/`get_export_config_path`/
`git_unavailable_reason` *on the `ghstars.cli` package itself*
(`monkeypatch.setattr(cli_module, "get_store", ...)`). A command module
importing those names directly (`from ghstars.cli.deps import get_store`)
would copy the original binding at import time and never see the patch.
Every command module instead does `from ghstars import cli` and calls
`cli.get_store()` etc. at call time, resolving live against whatever the
package's own namespace currently holds — same pattern `_render_records`
uses via `cli._render_records(...)`.

That live-lookup need is also what makes `cli/__init__.py` <->
`cli/commands/*` a genuine (legal, at runtime-safe) import cycle: `cli/
__init__.py` imports `commands` for registration; every command module
imports `cli` back for the live lookup. Runtime is fine (Python handles
this), but mypy's strict mode can't resolve `cli.app`'s type through that
cycle for `@cli.app.command(...)`-as-decorator usage specifically (`Cannot
determine type of "app"` / `Untyped decorator`). Fix: every command module
also imports `app`/`category_app` **by name** (`from ghstars.cli import
app`) for the decorator line only; `cli.<name>` stays for anything called
inside a function body. `app`/`category_app` are never reassigned, so a
direct import for them carries no monkeypatch risk the indirection was
protecting against for the other five names.

**Scope 2**: `apply_membership_diff()` now lives in `core/sync.py`
(renamed from `_apply_pushed_membership`, dropped the leading underscore
since it's cross-module now); `category.py` imports it instead of keeping
its own private copy. `category.py` already depended on `sync.py`
(`reconcile_list_membership`), so this adds no new import-cycle risk.

**Scope 3**: `_fetch_fresh_lists()` and `_undiverged()`, two small
module-level helpers in `category.py` itself (not promoted to `core/` —
both call sites are already in this one file; nothing outside it needs
them yet). `_undiverged(local, fresh_by_id)` is the one divergence check
`rename_category()` and `drain_category()` both had, byte-for-byte the
same shape once you account for each caller's own `old`/`from_category`
already equaling `local.category` by construction of how `targets`/
`from_targets` were filtered.

**Scope 4**: `tests/graphql_spy.py` (new, reusable) monkeypatches
`ghstars.github.client._graphql` — the module-level function every real
`RealGitHubClient` call funnels through — with a spy that records each
call's query text and always answers with a canned rate-limit-shaped
payload (valid for `check_rate_limit()`'s own parsing regardless of which
query was actually sent; the point is recording *which* queries happen,
not faking every response shape). `tests/test_no_auto_sync.py` launches a
real `RealGitHubClient`-backed `TuiApp` through `run_test()`, waits for
mount + its rate-limit worker, then asserts the recorded call list is
exactly `[_RATE_LIMIT_QUERY]`. Verified the mechanism actually catches a
violation (temporarily added an extra `fetch_lists()` call to `on_mount`
locally, confirmed the test fails, reverted before committing).
`spy_on_graphql(monkeypatch)` takes a `monkeypatch` fixture and returns
the call list — reusable as-is for a future ticket 14 test.

**Scope 5 (design decision)**: `tag_star()` gains an optional `lists:
list[List] | None = None` keyword parameter, and always returns the List
snapshot it actually used (raw fetch or caller-supplied, always
defensively `classify_list`-ed, plus any List it just created) on a new
`TagResult.lists` field. Omitted (every existing single-call-site caller:
`ghstars tag`, the design note left the TUI's own single-item path
unchanged too since it goes through the same bulk loop with a 1-star
target list), behavior is byte-for-byte the original per-call
`fetch_lists()`. The TUI's `_apply_tag` bulk-tag worker threads it: seeds
`lists = None`, passes each call's `result.lists` into the next
`tag_star()` call, so N stars into the same List costs at most one live
`fetch_lists()` for the whole batch instead of N. Full design rationale
(alternatives considered and rejected: a client-identity-keyed cache, a
separate bulk `tag_stars()` function) is a comment directly above
`tag_star()` in `core/tagging.py`, written before the implementation per
the ticket's instruction.

**Code review**: ran `/code-review` (medium) scoped to this diff after
implementation. Clean — no findings across correctness, dead-reference,
cross-file, reuse, simplification, efficiency, and conventions angles. No
fixes needed.
