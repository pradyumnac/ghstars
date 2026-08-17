# 07 — Category rename & drain

**What to build:** `ghstars category rename` renames a Category and updates all its Lists across Intents (Explore/Current/Retired variants) consistently in one operation, instead of the user manually renaming each variant. `ghstars category drain` bulk-migrates every Star from one Category into another. Any List created as a side effect of either operation follows the same public-by-default-with-`isPrivate`-override rule as ticket 04.

**Blocked by:** 04, 05.

**Status:** done

- [x] `ghstars category rename <old> <new>` renames all Intent-variant Lists for that Category consistently
- [x] `ghstars category drain <from> <to>` bulk-migrates all Stars from one Category to another
- [x] Lists created by rename/drain default to public unless an explicit `isPrivate` override is given
- [x] Both commands respect List-name validation from 03 (no malformed names produced)
- [x] `drain`/`rename` fetch fresh GitHub state before computing/writing the bulk change, and skip and report (never silently overwrite) any Star whose live List membership has already diverged from what triggered the migration

## Comments (post-implementation, 2026-08-17)

Implemented as a worktree agent.

**Design.** `ghstars category rename <old> <new>` renames every
Explore/Current/Retired List for `old`. Each renamed List keeps its own
Intent, under `new`. `ghstars category drain <from> <to>` moves each
Star out of `from`'s lifecycle Lists. Each Star lands in `to`'s List
with the same Intent. Explore stays Explore. Current stays Current.
Retired stays Retired. Neither command touches Reference Lists.
CONTEXT.md calls a Reference List's suffix a "Topic", not a "Category".
Neither command touches General Lists either — a General List has no
Category.

Added a new module, `ghstars.core.category`, with `rename_category()`
and `drain_category()`. Both functions hold `store.lock()` for their
full span. This matches `sync()` and `tag_star()`.

**The fresh-state-check rule.** Ticket 17's review added this
acceptance criterion. Both functions read `store.load_lists()` first.
This is the local snapshot that triggers the operation. Both functions
then call `client.fetch_lists()` for live GitHub state.
`drain_category()` also calls `client.fetch_stars()`. Both calls run
right before any write. Each target gets one check: does its live
state still match the local snapshot? A "no" answer means someone
renamed, reclassified, or deleted the target on GitHub since the last
sync. For `drain_category()`, a "no" answer can also mean a Star
already left the source List. On a "no" answer, the function skips
that target and reports it. Neither function writes over a target it
cannot confirm.

**No malformed names.** Both commands build a new List name the same
way: the Intent word, then `: `, then the user's category text.
`ghstars.core.taxonomy.parse_list_name()` always matches this exact
prefix first. So the result can never be malformed.
`rename_category()` also checks that the new name is not already taken
by a different live List. This stops it from creating a duplicate
name.

**Mutual exclusivity.** This is spec story 16, added by ticket 17.
Moved the sibling-stripping logic out of `tag_star()`. It now lives in
a new shared function, `ghstars.core.taxonomy.strip_lifecycle_siblings()`.
`tag_star()` calls this new function too — a pure refactor, same
behavior, same passing tests. `drain_category()` calls it as well.
Migrating a Star into `to_category` can add it to a second lifecycle
List for that Category. This happens when the Star already held an
unrelated List there. The shared function strips the old one, the same
way `tag_star()` already does.

**GitHub client.** Implemented `RealGitHubClient.update_list()`, over
the `updateUserList` mutation. Implemented `RealGitHubClient.delete_list()`,
over the `deleteUserList` mutation. Both were `NotImplementedError`
stubs since ticket 04. Verified both mutations' input and payload
shapes through live GraphQL introspection. This is a read-only check,
against the real account. No mutating call was made. No `ghstars`
command exposes `delete_list()` yet. No ticket asked for one. This
closes the class docstring's standing promise ("...until ticket 07"). A
future ticket can add a command that uses it — for example, one to
clean up the leftover `zzz-ghstars-verify-delete-me` test List from
ticket 04 (see HANDOFF.md).

**`/code-review` findings, all fixed:**
- `drain_category()` computed the migrated Stars from a fresh
  `client.fetch_stars()` snapshot. It then saved that whole snapshot
  back to `stars.json`. `fetch_stars()` always resets
  `pending_list_ids` to `None`. It always resets `archived` to
  `False`, on every Star it returns. The save would have silently
  wiped every other Star's staged `ghstars tag` edit. It would have
  wiped every other Star's Archived history too — not just the Stars
  the drain actually touched. This was a real, high-severity bug.
  Fixed: `drain_category()` now loads the existing local Stars on its
  own. It patches only the migrated Stars' `list_ids` onto that
  existing snapshot. It saves the patched snapshot, not the fresh one.
  New regression test:
  `test_drain_category_never_touches_an_unrelated_stars_local_state`.
- The CLI's success and warning messages echoed the raw argument text.
  The core functions strip that text before matching. A category name
  with stray whitespace would match correctly. But the message would
  print the stray whitespace back. Fixed: the CLI now strips both
  arguments up front, before it builds any message.
- `_category_not_found()` only ever calls `fail()`. `fail()` itself
  returns `NoReturn`. `_category_not_found()` was annotated `-> None`.
  Fixed to `-> NoReturn`, to match.

**Not flagged, a deliberate choice:** no CLI command exposes
`delete_list()`. No ticket asked for one. Adding a "category delete"
surface would be new scope, not a fix.

**Test status:** `mise run check` is clean — fmt, lint, mypy, and tests
all pass. 149 of 149 tests pass. `tests/test_category.py` has 20 new
tests. `tests/test_taxonomy.py` has 5 new tests, for
`strip_lifecycle_siblings()`. `tests/test_github_schema.py` has 4 new
tests, for `UpdateUserListResponse` and `DeleteUserListResponse`.
`tests/test_cli.py` has 7 new tests.
