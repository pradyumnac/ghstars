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

This rule is stricter than the released code. `strip_lifecycle_siblings`
applies the rule per Category today. It must apply the rule per Star.

### A lifecycle conflict fails the command

`tag` must refuse a tag that breaks the rule. The error names the List that
conflicts. `tag` removes no membership.

Automatic removal is wrong here. A conflicting List can hold the only record of
a subject, so a silent removal loses data, not only an Intent.

### The Category vocabulary lives in config

`ghstars.toml` holds the permitted Category values in a `[taxonomy]` table.
ADR 0009 assigns the setting to the core tier, because `core.taxonomy`,
`core.discovery` and `core.category` all read it. The user adds a value with a
text edit, not with a release.

A Category outside the vocabulary is kept and flagged `malformed`. It is never
rejected. ADR 0001 makes GitHub the source of truth, so the user can name a
List first and bless the value after.

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
- `strip_lifecycle_siblings` changes scope from the Category to the Star.
  Its callers in `core.tagging` and `core.category` change with it.
- `tag` gains a refusal path and a new error code. Existing tests that expect a
  silent strip need review.
- `core.config.CoreConfig` gains a `[taxonomy]` table beside `[export]`.
- `verify` gains two checks: an unblessed Category, and a Star in the triage
  inbox beside a classified List.
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
