# 0005 — Flat Category; List membership carries the second axis

## Status

proposed

## Implemented

n/a

## Context

A List name is `{Intent}: {Category}`. The Category slot holds one freeform
label. `parse_list_name` splits on the first colon-and-space separator. It
treats everything after the separator as the Category.

During the TUI design session on 2026-08-18 the user named two kinds of label:

- a **kind** of thing, for example `Dev Tools` or `CLI Tools`
- a **subject**, for example `AI`, `Game` or `DevOps`

This ADR first proposed to split the Category into two parts. A sub-separator
was to hold a kind and a subject as separate, queryable parts.

On 2026-09-09 the user renamed six Lists on GitHub. The new names used a
` - ` sub-separator, for example `Explore: Tool - Dev`. The renames made the
split decision urgent, so the team measured it against the account data.

### What the measurement showed

The data is 1,575 active Stars, 154 of them classified into 11 Lists.

The second axis does not hold as a hierarchy level:

- A broad `Dev` signal matches about 36 percent of the library. An axis that
  almost every Star shares gives no filtering power.
- The axis that does separate the Stars is the technology, for example Go,
  Python, Ansible or Neovim. That axis is open and high in cardinality. It is
  a tag set, not one hierarchy slot.
- Companion code carries no domain of use. One publisher supplies 187 Stars,
  which is 13 percent of the unclassified set.
- Each of the user's Lists holds one axis, never two. `Explore: Tool` groups
  by kind. `AI Agents Reference` groups by subject. Neither is a
  kind-and-subject cell.
- Seven Stars already belong to more than one List. `NousResearch/hermes-agent`
  needs two Lists under the split and under the flat model. List membership
  already carries the second axis.

### The objection this ADR first raised

The first version of this ADR rejected multi-List membership. It stated that a
Star in two Lists becomes adopted and candidate at the same time.

The objection is half correct. `strip_lifecycle_siblings` compares Categories,
so it permits `Current: Tool` beside `Explore: AI Agents`. The user confirms
that this pair is wrong. The answer is a stricter invariant, not a second
Category axis. See the Decision.

## Decision

### The Category stays flat

`List.category` stays `str | None`. The repo adds no hierarchy and no
migration. A Star that needs two subjects belongs to two Lists.

### `Learn` is a fifth Intent

`Intent` becomes `Explore`, `Current`, `Retired`, `Reference` and `Learn`.

`Learn` states why the user keeps a Star. It sits on the same axis as the
other four. `Learn` has no lifecycle, the same as `Reference`.
`LIFECYCLE_INTENTS` stays `{Explore, Current, Retired}`.

### A missing Intent prefix means `Reference`

A List name without an Intent prefix takes the `Reference` Intent. The whole
name becomes the Category. Every List has an Intent.

### Lifecycle exclusivity is global to the Star

A Star holds at most one lifecycle Intent across all of its Lists. `Reference`
and `Learn` have no limit.

`verify` reports a Star that breaks this rule. No command blocks on it.

Ticket 03 sets the pattern: ghstars flags a taxonomy problem for the user to
resolve, and never guesses. The user resolves a conflict with a rename or a
tag, because only the user knows which Intent is correct.

`strip_lifecycle_siblings` does not change. It keeps its per-Category scope.
That scope is what makes a `Current` to `Retired` move one call, which spec
stories 3, 16 and 17 require. A per-Star scope would instead delete the
membership that holds a second subject.

### ghstars never writes a name it cannot parse

`tag` must refuse to create a List when the name is malformed, or when the
Category is outside the vocabulary. The error names the problem. `tag` writes
nothing and removes no membership.

Ticket 07 already applies this rule to `category rename` and `category drain`:
both build a name from an Intent word, `: `, and the user's text, so neither
can produce a malformed name. `tag_star` takes the raw name from the user and
passes it to `create_list`, so `tag` is the one write path that can still
produce one.

A name that already exists on GitHub is different. ghstars keeps it and reports
it. ADR 0001 makes GitHub the source of truth, so ghstars never rejects what it
reads.

### `malformed` keeps its ticket 03 meaning

`List.malformed` means that the name attempts the Intent-prefix pattern and
fails, for example `Exploring: Foo`. It does not mean that the Category is
outside the vocabulary.

The two conditions need different repairs. A malformed name has one repair, a
rename. An unblessed Category has two: a rename, or a new entry in
`ghstars.toml`.

`verify` reports an unblessed Category. The `List` model gains no field, so the
CLI field sets do not change and ticket 14 keeps its contract.

### The Category vocabulary lives in config

`ghstars.toml` holds the permitted Category values in a `[taxonomy]` table.
ADR 0009 assigns the setting to the core tier, because `core.taxonomy`,
`core.discovery` and `core.category` all read it. The user adds a value with a
text edit, not with a release.

A Category outside the vocabulary is kept and reported as *unblessed*, a
condition distinct from `malformed` (see below). It is never rejected. ADR
0001 makes GitHub the source of truth, so the user can name a List first and
bless the value after.

### A Category can be a kind or a subject

The vocabulary holds both. `Tool` and `Library` are kinds. `AI Agents` and
`ML Research` are subjects. One flat slot holds either.

### The parser normalizes the derived Category

`classify_list` already derives `intent`, `category` and `malformed`. The
parser normalizes the derived Category only:

1. Change each underscore to a space.
2. Collapse each run of whitespace to one space.
3. Remove leading and trailing whitespace.

`List.name` keeps the GitHub value. The parser rewrites no name.

### `General` is a reserved Category

`General` marks a known Intent and an undecided subject. `Explore: General` is
the triage inbox.

A Star must not belong to the triage inbox and to a classified List at the same
time. `verify` must report a Star that breaks this rule.

## Consequences

- `parse_list_name` gains the normalization step and the missing-prefix rule.
  `ParsedListName` keeps its shape.
- `strip_lifecycle_siblings` does not change. `core.tagging` and
  `core.category` keep their current behaviour, and their tests keep passing.
- `tag` gains a refusal path and a new error code. It refuses a name it cannot
  parse, and a Category outside the vocabulary. It does not refuse a lifecycle
  conflict.
- `core.config.CoreConfig` gains a `[taxonomy]` table beside `[export]`.
- `verify` gains three checks: an unblessed Category, a Star in the triage
  inbox beside a classified List, and a Star with two lifecycle Intents.
  Only the first needs the vocabulary, so `verify_state` gains an optional
  argument that skips that one check. The other two always run.
- `verify_ok` widens in meaning. It covered corruption alone. It now also
  covers taxonomy drift, so a structurally clean account can report a
  problem. Any reader of `verify_ok` must expect that.
- `ghstars stars --category` and an `[export]` entry's `category` normalize
  the user's value, so `Dev_Library` still matches the stored `Dev Library`.
- `tag` reuses a List that parses to the same Intent and Category under a
  different spelling, instead of creating a duplicate.
- `export`'s `category` matcher keeps one axis. It does not change.
- The TUI Filter keeps one Category field. It does not become two filters.
- Six List names on GitHub flag as `malformed` after the next synchronization.
  That set is the triage worklist. The repo runs no rename.

## Alternatives considered

- **Compound Category, a kind and a subject in one name** — rejected. This ADR
  first chose it. The account data does not support it. See the Context.
- **One flat Category and text search** — accepted in part. The flat Category
  stays. List membership replaces text search for the second axis, because
  membership is already in use and it survives on github.com.
- **Local-only topic metadata, outside the List name** — rejected. It
  contradicts the premise that the taxonomy stays visible on github.com and in
  the phone app.
- **GitHub's own `repositoryTopics`** — rejected by the user. They are an
  uncurated folksonomy, and they compete with the user's taxonomy.

## Note on this file

The file name still reads `0005-compound-category-kind-and-subject.md`. The
decision reversed, and the number stays. Rename the file only with the ADR
index rebuild, so that no reference breaks.
