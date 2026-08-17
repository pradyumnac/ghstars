# 16 — Push a tag edit immediately, like unstar already does

**What to build:** make `ghstars tag` push its edit immediately, the same way `ghstars unstar` already does, instead of staging it as `pending_list_ids` for the next `ghstars sync` to push. This is **not** a generic "all write ops" ticket — analysis below shows `unstar` doesn't have the problem this ticket is about.

**Why `unstar` doesn't need this:** `unstar_cmd` already calls `client.remove_star()` for real, synchronously, and updates local state (`archive_star`, `remove_star_from_lists`) in the same command — no follow-up `ghstars sync` is needed for either GitHub or local state to reflect it. It's Star-existence (the Archived axis, ticket 06), not List-membership, so it was never going to go through ticket 05's three-way merge regardless of timing — there's no "wait for conflict arbitration" reason to defer it, and it doesn't. `tag` is the only current write command that requires a second command (`sync`) to actually take effect on GitHub.

**Blocked by:** 04, 05. Hard-blocked on 05 specifically: today, deferring the push doesn't actually buy any conflict-safety (see ticket 05's Comments — the current push is unconditional, not compared against anything). Making `tag` push immediately is only a *safe* trade once 05 exists and can run the same base-vs-current-vs-pending comparison synchronously inside `ghstars tag` itself, before pushing — otherwise this ticket would just be reintroducing the blind-overwrite problem 05 exists to fix, in a smaller window instead of a larger one.

**Status:** done

**Design (resolved 2026-08-17):**

- Immediate push lives in `core.tagging.tag_star()` itself, not just the CLI
  wrapper — `ghstars tag` and every TUI tag/retag/bulk-tag path share it, so
  all of them get the new behavior with no separate staging path anywhere.
- `tag_star()` computes the desired List-membership set (target added,
  lifecycle siblings stripped) from the `fetch_lists()` call it already makes
  today — i.e. fresh remote membership — not from local `star.list_ids` /
  `pending_list_ids`. This answers the ticket's original open question 1: no
  extra API call is needed, `tag_star()` already fetches all Lists for the
  List-existence check, and `List.items` already carries full remote
  membership.
- If local `star.list_ids` (base) differs from that fresh remote membership
  for this star, `tag_star()` does not compute or push any edit at all — it
  reports the specific diverged List(s) by name and stops. The user re-runs
  `ghstars sync`, then retries `ghstars tag`. No auto-rebase, no silent
  GitHub-wins resolution at tag-time.
- A push failure for any other reason (network/API error, target List
  deleted concurrently) fails the command outright with no local write at
  all — mirrors `unstar_cmd`'s remote-first, write-only-on-success pattern.
  No fallback staging. This answers open question 2: staged-and-deferred
  does not become a fallback path, it disappears from every reachable call
  site (see ADR 0004 for why the underlying types/functions stay in the
  codebase anyway).
- TUI bulk-tag gets the same per-star immediate-or-fail semantics as
  single-tag (no queue, no deferred batch). New work as part of this ticket:
  batch the repo→node-ID lookups for every targeted star into a single
  request before pushing (today `_resolve_repository_node_id` is called
  once per item, with no batching anywhere) — advisor analysis found this
  halves bulk-tag's round-trip count for free, since GitHub's rate-limit
  points are charged by query complexity, not request count. The membership
  mutations themselves stay sequential, one per star, preserving today's
  per-star failure isolation and incremental TUI progress — full mutation
  batching via GraphQL aliasing was considered and rejected (breaks
  request-level failure isolation, breaks incremental progress, adds real
  complexity, and doesn't save rate-limit points) unless future profiling
  shows the lookup-batch alone isn't enough. This answers open question 3.
- `pending_list_ids`, `_merge_pending_list_membership`, `RetriageEntry`, and
  `ghstars retriage` are left in place, unmodified — see ADR 0004.

**Acceptance criteria:**

- [x] `tag_star()` computes the new desired List-membership set from fresh
      remote membership (the existing `fetch_lists()` call), not from local
      `star.list_ids`/`pending_list_ids`
- [x] If local `star.list_ids` differs from that fresh remote membership,
      `tag_star()` raises/reports before computing or pushing any edit,
      naming the specific diverged List(s); nothing is pushed, nothing is
      staged
- [x] Otherwise, `tag_star()` pushes the new desired set immediately via
      `client.update_list_membership_for_item` in the same call — no
      `pending_list_ids` staging on the happy path
- [x] On any other push failure, `tag_star()`/`ghstars tag` fails outright;
      no local state is written
- [x] `ghstars tag`'s help text and success/failure messaging drop "run
      `ghstars sync` to push it" — the edit is already live once the command
      succeeds
- [x] TUI tag/retag/bulk-tag actions get the same behavior automatically
      via the shared `tag_star()`, with no separate staging path
- [x] TUI bulk-tag batches repo→node-ID lookups for all targeted stars into
      one request; membership-update mutations remain sequential and
      isolated per star, same as today
- [x] `pending_list_ids`, `_merge_pending_list_membership`, `RetriageEntry`,
      `ghstars retriage` are untouched by this ticket's changes (see ADR
      0004); their existing tests keep passing unchanged
- [x] New tests: drift-detected blocks and names the diverged List(s);
      no-drift computes from remote and pushes; push failure leaves no
      local write; bulk-tag batches node-ID lookups

## Comments (2026-08-17)

Ticket 05 landed on `main` (`e48b704`) — the hard-block above is now
resolved, `tag_star()` has the three-way-merge logic (in
`core/sync.py`'s `_merge_pending_list_membership`) to call synchronously
once this ticket is actually designed. Not picking this up yet: the
current session is holding all new ticket work (this one included) until
the spec/issues consistency audit's findings (story 4 default, story 16
Intent mutual exclusivity, etc. — see `HANDOFF.md`) are solutioned and
resolved.

## Comments (2026-08-17, design session)

Design resolved through a structured grilling session with the user,
grounded in a live grep of every `pending_list_ids` call site and a
dedicated advisor sub-agent pass on the bulk-push-batching question. All
three original open questions are answered above under **Design**; full
acceptance criteria added. Notably, the user chose to keep
`pending_list_ids`/`_merge_pending_list_membership`/`RetriageEntry`/
`ghstars retriage` in the codebase rather than remove them, even though
this ticket makes them unreachable — recorded as ADR 0004 rather than
silently deleted, since a future reader would otherwise have no way to
know that was deliberate. Not yet implemented — status moved to
`ready-for-agent — speced`, blockers 04/05 both already `done`.

## Comments (2026-08-17, implementation)

Implemented directly in the main session (not a worktree agent):
`tag_star()` (`core/tagging.py`) now computes the desired List-membership
set from the same `fetch_lists()` call it already made, raises
`StarListMembershipDriftError` (naming diverged Lists by name) if local
`list_ids` disagrees with it, and pushes immediately via
`client.update_list_membership_for_item`/`update_list_membership_for_node`
inside the same `store.lock()` span — only writing `stars.json`/
`lists.json` after a successful push. A push failure raises
`TagPushError`; no local write happens either way. `GitHubClient` gained
two new Protocol methods (`update_list_membership_for_node`,
`resolve_repository_node_ids`), implemented in both `FakeGitHubClient` and
`RealGitHubClient` (the latter via a new aliased-GraphQL batched query,
`_batched_repository_id_query`). The TUI's bulk-tag path
(`tui/app.py::_apply_tag`) resolves every target's node ID in one batched
call when there is more than one target, threading each result into
`tag_star(..., node_id=...)`; a single target skips the batch call
entirely. `_refresh_table()`'s old "[pending sync]" display is gone —
`list_ids` is already live. `pending_list_ids`,
`_merge_pending_list_membership`, `RetriageEntry`, `ghstars retriage` are
untouched (ADR 0004).

Existing tests across `test_tagging.py`, `test_cli.py`, and `test_tui.py`
were rewritten where their fixtures/assertions encoded the old
staged-edit model (several also needed a `List.items` fix so local
`list_ids` and remote membership agree, since the drift check is now
live). New tests added: drift detection and message content
(`test_tagging.py`), push-failure-leaves-no-local-write
(`test_tagging.py`), pre-resolved-node-id usage (`test_tagging.py`),
stale-`pending_list_ids`-is-ignored (`test_tui.py`), bulk-vs-single
node-ID batching (`test_tui.py`), and `RealGitHubClient`'s new batched
query/mutation methods (new file `test_repository_id_batching.py`).
`docs/explanation/known-limitations.md` updated: the "pending tag pushes"
section now describes the immediate-push model and the TUI's ID-lookup
batching, not the old staged/sync-time push.

`/code-review` ran against the full diff and found four issues, three
fixed, one deliberately left as documentation only:

- **Fixed** — `store.lock()` now spans `tag_star()`'s GitHub push (up to
  two more `gh api graphql` round trips on top of the pre-existing
  `fetch_lists()`/`create_list()` calls already inside the lock), which
  can make a concurrent `ghstars` command's own lock acquisition exceed
  its 5s default timeout and crash with a raw `filelock.Timeout`.
  `tag_cmd` now catches `Timeout` and fails cleanly instead. (The same
  underlying gap exists more broadly — `sync`/`unstar`/`category` never
  caught `filelock.Timeout` either, before or after this ticket — worth
  a dedicated follow-up ticket if it proves to matter in practice, out
  of scope here.)
- **Fixed** — `tag_star()` was writing `lists.json` twice per call (once
  unconditionally after the List-existence check, once again after a
  successful push), even when no new List was created. The first write
  is now conditional on actually having just created a List — it still
  persists new-List-creation immediately even if the call fails later,
  which is the property it exists for.
- **Fixed** (drive-by, found while addressing the above) — a comment on
  the push's `except Exception as exc:` block lost its lead line to a
  `ruff format` pass mid-implementation, leaving an orphaned, broken
  sentence. Corrected to match the established one-line `# noqa: BLE001
  -- see docstring above` convention used elsewhere in this file.
- **Documented, not changed** — in a TUI bulk-tag batch, `tag_star()`'s
  drift check for star N+1 only sees star N's own already-applied
  change (via the threaded `lists` snapshot + `apply_membership_diff`),
  not a change some *other* process makes directly to star N+1 while
  star N's push is still in flight. Closing this gap would mean a live
  `fetch_lists()` per star, exactly the round-trip cost the `lists`-
  threading optimization (ticket 19 scope 5) exists to avoid — the same
  eventual-consistency trade already accepted for List-creation races
  in the same threaded batch (see the design note atop `tagging.py`).
  Documented explicitly on `tag_star()`'s and `_apply_tag()`'s
  docstrings rather than left implicit. A single (non-bulk) `ghstars
  tag` call never threads `lists`, so it does not have this gap.
- **Not a finding, but reviewed** — the push-then-write ordering means a
  local write failure (`store.save_stars`/`save_lists`) *after* a
  successful GitHub push would leave GitHub and local state silently
  diverged. This is inherent to the remote-first pattern this ticket
  deliberately mirrors from `unstar_cmd`, which has the identical gap
  already, unaddressed — fixing it asymmetrically in only one of the two
  commands would be inconsistent, so left as-is pending a dedicated pass
  across both if it proves worth doing.

`mise run check` (fmt/lint/typecheck/test) re-run after fixes: 206/206
tests passing, fmt/lint/mypy clean.
