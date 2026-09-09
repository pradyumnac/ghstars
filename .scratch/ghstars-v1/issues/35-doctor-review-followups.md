# 35 — Open items from the doctor flow review

**What this records:** The items an independent review of the taxonomy and
doctor work left open on 2026-09-09. Each was reported as unresolved without a
ticket, so none of it counted as tracked work. This ticket is that record.

**Status:** needs-triage — items A and B are ready; C, D and E need a product
decision.

**Kind:** enhancement

**Blocked by:** None. Items C, D and E wait on the user, not on code.

## A — Widen stale-classification detection (ready)

`stale_classification_warning` only finds a List with `intent=None` and
`malformed=False`. It misses every other shape of a record written by an older
parser:

- an un-normalized Category, for example a stored `Dev_Library`
- old whitespace, for example a stored `" Skills"`
- a `Learn:` List the old parser marked malformed

Comparing the stored `intent`/`category`/`malformed` against
`classify_list(lst)` detects all three.

**Design note.** Detection is not the only option, and may not be the right
one. These three fields are a pure function of `List.name`, stored in the same
record, so the root cause is persisting a derived value at all. Deriving them
on access -- a pydantic `computed_field` -- makes the staleness class
unreachable rather than merely visible, and removes `classify_list` and its
seven defensive call sites. Measured cost on 2026-09-09: 4 failing tests out of
524, all of them records whose stored value contradicted the name.

Decide detect-or-eliminate before building either. The `StateStore` must stay
a dumb container in both designs.

## B — Ticket 34 status (ready)

Ticket 34 reads `ready-for-human` with `Blocked by: None` while these items
stay open. Correct it, or point it here.

## C — TUI and Category commands bypass the vocabulary (needs a decision)

`tui/app.py` calls `bulk_tag_stars()` with no `categories`, and
`core/category.py` never calls `check_writable_list_name`. The TUI can create a
List that `ghstars tag` refuses.

ADR 0005 already says ghstars never writes an unblessed name, so refusal is the
default and warn-and-proceed is what needs an ADR change. The open question is
narrower: whether refusing part-way through a TUI flow is acceptable, or
whether the TUI needs a different presentation of the same refusal.

## D — Existing semantic duplicate Lists (detection ready, repair blocked)

`rename_list` stops a new duplicate. Nothing reports a pair already on GitHub
that parses to one `(intent, category)`, and `_find_list` binds to whichever
GitHub returns first.

ADR 0005 makes bare and explicit forms one List, which makes a duplicate a
defect by that decision's own logic. Detection can land now. The repair cannot:
which List survives, and whether membership merges, is a product decision.

## E — `bootstrap` cannot bind to a reviewed plan (needs a decision)

`doctor` fetches, then `bootstrap` fetches again and re-derives its own target
set. A List created between the two changes what gets made. `--category`
narrows the window; it does not close it.

Accept the race, or require plan stability.

## F — `remote bootstrap` versus the explicit-target contract

`docs/reference/cli.md` states a global rule: "A mutation always names its
target explicitly. No command accepts a Filter, a search term, standard input,
or a wildcard as a mutation target (Scope 4)."

`remote bootstrap` with no `--category` mutates every missing Category, which
is a wildcard target. Resolve one way or the other: require at least one
`--category`, or document `bootstrap` as an explicit exception to the rule.

## Comments

The review also found that `mise run check` was not a gate: it ran
`ruff format .` and `ruff check --fix .`, which repair the tree instead of
failing on drift, so it could pass while leaving uncommitted changes. Fixed on
2026-09-09 -- `check` is now verify-only and a separate `fix` task carries the
mutating commands.
