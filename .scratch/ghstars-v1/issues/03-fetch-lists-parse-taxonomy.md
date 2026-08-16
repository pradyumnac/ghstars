# 03 — Fetch Lists & parse taxonomy

**What to build:** Sync also pulls the user's existing GitHub Lists and their membership (`viewer.lists`), so classification already done on github.com is respected, not overwritten. List names parse into `Intent` (`Explore`/`Current`/`Retired`/`Reference`/`None` for General) and `Category` per the `{Intent}: {Category}` convention. Names that don't conform (e.g. an existing unprefixed "Vendored skills" list) are flagged as needing a rename rather than silently guessed at. Unclassified new stars land in `Explore: General` by default.

**Blocked by:** 02.

**Status:** done

- [x] Sync fetches `viewer.lists` (id, name, slug, description, isPrivate, items) alongside stars
- [x] List names parse into Intent/Category; `Explore`/`Current`/`Retired`/`Reference` recognized, General (no prefix) recognized
- [x] Malformed names are flagged for the user to resolve, never auto-assigned an Intent
- [x] `ghstars lists --json --fields intent,category` reflects parsed classification for real Lists (see Comments: reinterpreted as a new `lists` command)
- [ ] New unclassified stars default to `Explore: General` -- deliberately deferred to ticket 04 (see Comments)

## Comments

Implemented `RealGitHubClient.fetch_lists()` over `gh api graphql` (`viewer.lists`
for id/name/slug/description/isPrivate, paginated via the existing
`_paginate_all` helper; each List's `items` fetched via a separate per-list
`node(id:) { ... on UserList { items(...) } }` paginated query rather than
resuming the outer connection's cursor -- one extra `gh` call per List, judged
fine at personal-CLI scale, same call as ticket 02's "sequential is fine, not
worth threading" precedent). Schema verified live via introspection
(`UserList`, `UserListConnection`, `UserListItemsConnection`, the
`UserListItems` union's only possible type is `Repository`) and cross-checked
against the real authenticated account: 6 real Lists, including the two
unprefixed ones (`Vendored skills`, `AI Agents Reference`) mentioned below.

Added `ghstars.core.taxonomy.parse_list_name()`/`classify_list()`. Applied in
`core/sync.py` as a small, separate block (fetch Lists, classify, save) added
after the existing star-fetching, per the instruction to keep that file's
diff minimal and mergeable against ticket 06's parallel changes to `sync()`
(a merge conflict there is expected, left for the supervisor).

**Doc inconsistency (spec.md vs CONTEXT.md), and how I resolved it:**
spec.md's "Naming convention & validation" section says validation should
flag the account's actual unprefixed `Vendored skills` list "as needing a
rename." Read literally, that contradicts CONTEXT.md's own General List
definition: "A List with no Intent prefix -- freeform, outside the taxonomy
entirely" -- described there as a first-class, deliberate category, not an
error. I treated CONTEXT.md as authoritative (it's the domain glossary, and
`docs/agents/domain.md` names it as the thing to read first): a plain
unprefixed name -- `Vendored skills`, `AI Agents Reference`, `Explore Zone`,
even bare `Explore` -- parses as valid General (`intent=None`,
`malformed=False`). "Malformed" (`malformed=True` on `List`, a new field) is
reserved for names that look like an *attempt* at the Intent-prefix pattern
but don't exactly match: wrong case (`explore: Foo`), wrong separator
(`Explore - Foo`, `Explore-Foo`), or any `{word}: {rest}`-shaped name where
`word` isn't one of the four exact canonical Intent strings (`Exploring: Foo`).
That last sub-rule is intentionally broad -- any name shaped like
`{word}: {rest}` where `word` doesn't exactly match gets flagged, even though
it could false-positive on a deliberately colon-containing freeform General
name (e.g. a hypothetical `Notes: Misc` General list). Flagging this now so
the user can revisit via `/domain-modeling` if they'd rather CONTEXT.md's
General definition explicitly carve out an escape hatch for that case, or if
spec.md's example was simply describing a soon-to-be-renamed list rather than
a validation rule at all.

**`ghstars lists` command interpretation:** the ticket's acceptance criterion
literally says `ghstars list --json --fields intent,category`, but the
existing `list` command (ticket 01) operates on `Star`, validated against
`Star.model_fields` -- `intent`/`category` aren't Star fields and would
hard-fail as unknown. Added a new, separate `ghstars lists` (plural) command
instead, following the exact same `--json`/`--fields`/hard-fail conventions,
validated against `List.model_fields`. Verified live:
`ghstars sync && ghstars lists --json --fields name,intent,category,malformed`
returns the 6 real Lists with correct parsed classification.

**Ticket's last checkbox ("new unclassified stars default to `Explore:
General`") deliberately not implemented here** -- per explicit scope
clarification from the supervisor: actually wiring a Star into `Explore:
General` on creation requires writing List membership back to GitHub
(`create_list`/`update_list_membership_for_item`), which still raise
`NotImplementedError` pending ticket 04 (local tagging + push). Ticket 03's
job was fetching/parsing Lists correctly, which is done and verified; the
write-back is ticket 04's.

**`/code-review` findings, all fixed:**
- `parse_list_name()` flagged *any* name whose leading word case-insensitively
  matched an Intent as malformed, even with no separator attempt at all --
  `"Explore Zone"`, bare `"Explore"`, `"Current Events"` were false-flagged.
  Fixed by only treating it as an attempted prefix when what follows the
  leading word looks like a separator attempt (optional whitespace then `:`
  or `-`), not a normal word boundary.
- `sync()` saved Stars before fetching Lists, so a `fetch_lists()` failure
  after `save_stars()` succeeded left `stars.json` fresh and `lists.json`
  stale. Fixed by fetching both stars and Lists before saving either.
- `sync_cmd`'s plain-text output only reported `star_count`, dropping the new
  `list_count`. Fixed.
- `list_cmd`/`lists_cmd` duplicated the `--json`/`--fields`/hard-fail
  rendering logic almost verbatim. Extracted into a shared
  `_render_records()` helper (PEP 695 generic over `BaseModel`, matching the
  `_paginate_all[T]` generic-function style already used in
  `ghstars.github.client`).

Not flagged/not changed: the deferred `Explore: General` auto-assignment
(discussed above, ticket 04's job).

Final `mise run check`: fmt/lint/typecheck/test all clean, 47 tests passing.
