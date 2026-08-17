# 19 — Architecture cleanup from the 07/09/10/11 advisor review

**What to build:** five structural cleanups, all originating from the
2026-08-17 whole-project advisor review over the merged 07/09/10/11 layer
(see `HANDOFF.md`'s now-landed "Architecture-improvement suggestions"
section for full traceability — this ticket is the landing place, replacing
that section as the source of truth going forward). None of these change
user-facing behavior; all are report-only findings the user asked to be
addressed before ticket 08.

**Blocked by:** none (07, 09, 10, 11 are all done).

**Status:** ready-for-agent

## Scope 1 — Split `cli/__init__.py` into per-command modules

- [ ] `src/ghstars/cli/__init__.py` (532 lines across ~10 commands) is
      split into `cli/commands/{sync,list_lists,tag,unstar,retriage,category,
      export,diff,tui}.py` (exact grouping left to the implementer — group
      by feature, not 1:1 per command, where commands are tightly related),
      each registering its command(s) on the shared `app`/`category_app`
      Typer instances.
- [ ] `cli/__init__.py` itself shrinks to app/`category_app` construction,
      shared helpers used by multiple command modules (e.g.
      `_render_records`), and importing/registering the command modules —
      mirroring how `core/__init__.py` already re-exports from submodules.
- [ ] No command's behavior, help text, or `--json`/`--fields` contract
      changes — this is a pure module reorganization, covered by the
      existing `test_cli.py`/`test_cli_diff.py`/etc. test suites passing
      unchanged.

## Scope 2 — Consolidate duplicated List-membership-mirroring logic

- [ ] `sync.py::_apply_pushed_membership` and
      `category.py::_apply_membership_diff` are near-identical logic for
      mirroring a membership push onto `List.items` — `category.py`'s own
      docstring already admits it's a private copy rather than an import.
      Extract one shared helper (in `core/`, wherever fits best without
      creating an import cycle between `sync.py` and `category.py`) and have
      both call sites use it.
- [ ] Existing `test_sync.py` and `test_category.py` coverage for both call
      sites passes unchanged against the shared helper.

## Scope 3 — Consolidate the "fetch fresh, skip diverged" pattern

- [ ] `category.py`'s `rename_category()` and `drain_category()`
      independently implement "fetch fresh GitHub state, skip and report
      any item that diverged from the local snapshot that triggered this."
      Extract a shared "fetch-and-diff-against-local-snapshot" primitive
      that both call, so a future ticket-07-shaped command doesn't
      reimplement it a third time.
- [ ] Existing `test_category.py` coverage for both commands' skip-diverged
      behavior passes unchanged against the shared primitive.

## Scope 4 — Mechanically enforce the no-auto-sync guarantee (ADR 0003)

- [ ] Add a test that asserts `ghstars tui`'s bare launch (`on_mount`, no
      user interaction) makes zero calls through `GitHubClient`'s
      `_graphql()` chokepoint other than `check_rate_limit()` — turning
      [ADR 0003](../../../docs/adr/0003-github-sync-is-always-explicit.md)'s
      rule into something CI checks automatically, rather than relying on
      manual review each time a new layer merges.
- [ ] The mechanism (a call-counting fake/spy around `_graphql()`, or
      equivalent) is left to the implementer, but must be reusable for a
      future ticket 14 (agent skill) test making the same assertion.

## Scope 5 — Reduce `tag_star()`'s redundant `fetch_lists()` cost

- [ ] `tag_star()` (`core/tagging.py`) re-fetches Lists live on every call,
      by design (see its own docstring). Bulk-tagging N stars into the same
      List today costs N redundant `fetch_lists()` calls — already flagged
      as a deferred issue in `tui/app.py`'s `_apply_tag` docstring.
- [ ] **Needs a design decision during implementation, not just guessed
      at**: the shape of the fix is open — e.g. `tag_star()` gaining an
      optional pre-fetched `lists` parameter that a caller doing a bulk
      operation (the TUI's bulk-tag action) can supply once instead of
      per-star. Whoever picks up this scope should propose the seam shape
      as a comment before implementing it, since it changes `tag_star()`'s
      signature and every existing call site.
- [ ] Existing `test_tagging.py` and `test_tui.py` coverage for `tag_star()`
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
