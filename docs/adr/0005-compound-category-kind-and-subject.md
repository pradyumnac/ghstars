# 0005 — Compound Category: a kind and a subject in one List name

## Status

proposed

## Implemented

n/a

## Context

A List name is `{Intent}: {Category}`. The Category slot holds one freeform
label. `parse_list_name` splits on the first colon-and-space separator, and
treats everything after it as the Category.

During the TUI design session (2026-08-18) the user named two different kinds
of label they want to use:

- a **kind** of thing — `Dev Tools`, `CLI Tools`, `Self-Hosted Tools`
- a **subject** — `AI`, `Game`, `Server`, `DevOps`

One slot cannot hold both as separate, queryable parts. A repo such as
`langchain` is a dev tool and it is AI. Today the user must choose one label,
or fuse the two into one string such as `AI Dev Tools`.

Three ways to hold both were examined:

- Put the Star in two Lists, `Current: Dev Tools` and `Explore: AI`. This is
  legal today, because a Star can belong to many Lists. It breaks the one
  invariant the taxonomy has: `strip_lifecycle_siblings` enforces
  Explore/Current/Retired exclusivity **per Category**, so the same Star
  becomes adopted and candidate at the same time.
- Keep one freeform Category and find cross-cutting sets with text search.
  This costs nothing and works today.
- Split the Category into two parts with a sub-separator.

The user chose the split, and asked for it as a follow-up, not as part of the
TUI work.

## Decision

*Not yet decided.* The direction is chosen: a Category can carry a kind and a
subject as separate, queryable parts. The mechanism is open.

Resolve these before this ADR can be accepted:

- Which sub-separator? A candidate is `/`, giving `Explore: Dev Tools / AI`.
  It must not collide with a character users already put in List names.
- Is either part optional? `Explore: Dev Tools` and `Explore: AI` must stay
  valid, or every existing List needs a rename.
- Which part drives Intent exclusivity — the kind, the subject, or the whole
  compound? This decides whether `Current: Dev Tools / AI` and
  `Explore: Dev Tools / Game` can hold the same Star.
- What happens to the 7 Lists on the real account? Migration, or grandfather
  them as kind-only Categories.
- Which part drives the TUI's derived colour (spec story 60)?

## Consequences

If accepted:

- `parse_list_name` and `ParsedListName` change shape, and every caller of
  `List.category` must state which part it means.
- `strip_lifecycle_siblings` changes, because it compares Categories.
- `export.toml`'s `category` matcher gains a second axis.
- The TUI Filter (spec story 54) becomes two filters, not one.

Until accepted, spec stories 50-72 assume one freeform Category. The Filter
design must leave room for a second axis, and must not hard-code a single
Category field into its public shape.

## Alternatives considered

- **One freeform Category plus text search** — passed over, but it is the
  fallback if the questions above have no clean answer. It needs no parser
  change, no migration, and it keeps "the List name is the whole taxonomy"
  literally true. `Explore: AI` and `Explore: Dev Tools` are already both
  valid Categories.
- **A Star in two Lists, one per axis** — rejected. It breaks Intent
  exclusivity, as shown above.
- **Local-only topic metadata, outside the List name** — rejected. It
  contradicts the project's core premise that the taxonomy stays visible and
  usable from github.com and the phone app.
- **GitHub's own `repositoryTopics`** — rejected by the user. They are an
  uncurated folksonomy, and they would compete with the user's taxonomy.
