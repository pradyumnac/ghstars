# 33 — List name syntax drift between the account and the repo

**What this records:** The user renamed six Lists on GitHub. The new names use
a syntax that the repo does not model. This ticket records the measured
difference and the direction decision. It does not hold the implementation
plan.

**Status:** ready-for-human — the code and the remediation landed on
2026-09-09. Five items remain open; see "Pending" below. One needs a
product decision, one is ready to build, three ride with ticket 14 (P3's
decision is made; P6/P7 always did). P1 and P2 are resolved.

## Remediation, executed 2026-09-09

The user ran `ghstars sync`, then the four flagged names were resolved:

| List | Repair | How |
| --- | --- | --- |
| `Explore: Tool - Dev` | blessed `Tool - Dev` in `[taxonomy]` | config edit, no GitHub write |
| `Explore: Tool - CLI` | blessed `Tool - CLI` in `[taxonomy]` | config edit, no GitHub write |
| `Explore: Dev_Library` | renamed to `Explore: Library` | `ghstars category rename "Dev Library" "Library"` |
| `Learning` | renamed to `Learn: General` | `client.update_list()` directly -- no existing command covers a bare-name-to-`Learn`-prefixed rename |

`ghstars doctor` confirmed `Names: ok` afterward. The rename exposed a
follow-on finding: see ticket 34.

**Blocked by:** None.

**Evidence:** Live GraphQL query of `viewer.lists` on 2026-09-09, account
`pradyumnac`, 11 Lists. Local store at `~/.ghstars/state/lists.json`, last
synchronized 2026-08-30. Parser output from
`ghstars.core.taxonomy.parse_list_name` against the live names. The local store
and the live account match by List `id`, so each difference below is a rename,
not a delete and a create.

## What changed on GitHub

The user renamed six Lists between 2026-08-30 and 2026-09-09. The local store
holds the old names. A synchronization will apply every rename at once.

| Old name (local store) | New name (GitHub) | Items |
| --- | --- | --- |
| `Explore: Possible Dev Tooling` | `Explore: Tool - Dev` | 10 → 13 |
| `Explore: Possible Dev Library` | `Explore: Dev_Library` | 4 → 5 |
| `Explore: Vendored Skills` | `Explore:  Skills` | 13 → 14 |
| `Reference: ML Research` | `ML_Research` | 1 → 1 |
| `AI Agents Reference` | `AI_Agents` | 10 → 11 |
| `Vendored skills` | `Skills` | 3 → 3 |

GitHub also holds one new List, `Explore: Tool - CLI`, with 3 items. GitHub no
longer holds `zzz-ghstars-verify-delete-me`, a test artifact with 1 item.

Four names keep their old value: `Explore: General`, `Explore: Tool`,
`Reference: General` and `Learning`.

The renames drop the qualifier words `Possible` and `Vendored`. The renames
also introduce the `-` and `_` characters. Findings 1 to 6 measure the result.

## What the repo expects

`CONTEXT.md` and `core/taxonomy.py` define the convention.

| Rule | Definition |
| --- | --- |
| Name format | `{Intent}: {Category}` |
| Intent values | `Explore`, `Current`, `Retired`, `Reference` |
| Separator | A colon and one space. |
| Unprefixed name | A General List. It has no Category. |
| Category | One opaque string after the prefix. The repo does not split it. |
| Lifecycle rule | `Explore`, `Current` and `Retired` are mutually exclusive per Category. |
| Sibling match | `strip_lifecycle_siblings` compares two Category strings for equality. |
| Malformed name | A name that attempts the Intent prefix and fails. |

## What the account contains

| Name | Items | Repo reads Intent | Repo reads Category | Malformed |
| --- | --- | --- | --- | --- |
| `Explore: General` | 110 | `Explore` | `General` | No |
| `Explore:  Skills` | 14 | `Explore` | `" Skills"` | No |
| `Explore: Tool - Dev` | 13 | `Explore` | `Tool - Dev` | No |
| `AI_Agents` | 11 | None | None | No |
| `Explore: Tool` | 8 | `Explore` | `Tool` | No |
| `Explore: Dev_Library` | 5 | `Explore` | `Dev_Library` | No |
| `Explore: Tool - CLI` | 3 | `Explore` | `Tool - CLI` | No |
| `Skills` | 3 | None | None | No |
| `Learning` | 2 | None | None | No |
| `ML_Research` | 1 | None | None | No |
| `Reference: General` | 0 | `Reference` | `General` | No |

The parser flags no name as malformed. Every difference below is silent.

## Finding 1 — The account uses a sub-Category level

The account uses ` - ` to make a child Category. `Explore: Tool`,
`Explore: Tool - Dev` and `Explore: Tool - CLI` form one group for the user.

The repo reads three unrelated Categories: `Tool`, `Tool - Dev` and
`Tool - CLI`. The repo has no parent-child level.

Consequence: the lifecycle rule does not hold across the group. A move from
`Explore: Tool - Dev` to `Current: Tool` strips no sibling, because
`strip_lifecycle_siblings` compares `"Tool - Dev"` to `"Tool"` and finds no
match.

## Finding 2 — A double space makes a hidden Category

`Explore:  Skills` contains two spaces. The parser matches the prefix
`"Explore: "` and returns the Category `" Skills"` with a leading space.

The parser does not strip the space. The parser does not flag the name.

Consequence: a later `Explore: Skills` becomes a second, different Category.
Both names produce the slug `explore-skills` on GitHub.

**Triage (2026-09-09):** This is a data defect, not a design defect. The name
holds a typo. The rename from `Explore: Vendored Skills` introduced the typo.
Correct the data. Rename the List on GitHub to `Explore: Skills`. A List rename
is a live mutation, so get approval before you run it.

## Finding 3 — Two word separators are in use

`Dev_Library`, `AI_Agents` and `ML_Research` join words with an underscore.
`Tool - Dev` and `Tool - CLI` join words with a spaced dash.

The repo normalizes neither form. `Dev_Library` and `Dev Library` are two
Categories.

## Finding 4 — `General` has two meanings

`CONTEXT.md` reserves "General List" for a List with no Intent prefix and no
Category.

The account also uses `General` as a literal Category in `Explore: General`
and `Reference: General`. The repo stores the Category string `General` for
both.

`Explore: General` holds 110 of the tagged Stars.

## Finding 5 — Related names sit on both sides of the taxonomy

`Skills` is a General List with no Category. `Explore:  Skills` carries the
Category `" Skills"`. The repo cannot relate the two Lists.

The same pattern can apply to `AI_Agents`, `ML_Research` and `Learning`.

## Finding 6 — The fake client builds the wrong slug

`core/fake_client.py:38` builds a slug with
`name.lower().replace(" ", "-").replace(":", "")`.

GitHub produces a different slug. The observed GitHub rule is: change the name
to lower case, replace each run of characters outside `a-z` and `0-9` with one
dash, then remove a leading or trailing dash.

Six of the 11 names diverge.

| Name | GitHub slug | Fake client slug |
| --- | --- | --- |
| `Explore: Tool - Dev` | `explore-tool-dev` | `explore-tool---dev` |
| `Explore: Tool - CLI` | `explore-tool-cli` | `explore-tool---cli` |
| `Explore: Dev_Library` | `explore-dev-library` | `explore-dev_library` |
| `Explore:  Skills` | `explore-skills` | `explore--skills` |
| `AI_Agents` | `ai-agents` | `ai_agents` |
| `ML_Research` | `ml-research` | `ml_research` |

Scope limit: the repo stores `slug` but never matches on it. `core/tagging.py`
matches a List by `name`. Other paths match by `id`. Finding 6 affects test
fidelity, not production matching.

## Finding 7 — A rename removed the Reference Intent

The rename of `Reference: ML Research` to `ML_Research` removed the Intent
prefix.

| State | Intent | Category |
| --- | --- | --- |
| Local store, 2026-08-30 | `Reference` | `ML Research` |
| GitHub, 2026-09-09 | None | None |

The List drops out of the Intent taxonomy. It becomes a General List. The
Category `ML Research` stops existing.

The rename of `AI Agents Reference` to `AI_Agents` removed the word
`Reference` from the end of the name. The repo reads both the old name and the
new name as a General List, because an Intent must start the name. The Intent
taxonomy does not change for this List. The user intent is unclear.

Decide whether these two Lists must carry the `Reference` Intent. A
synchronization applies the current GitHub names and makes the loss permanent
in the local store.

## Finding 8 — Two renames encode one shape in two orders

Two renames describe the same shape: a thing, scoped to a domain of use. The
two results disagree on both word order and separator.

| New name | Order | Separator | Thing | Domain |
| --- | --- | --- | --- | --- |
| `Explore: Tool - Dev` | thing first | ` - ` | `Tool` | `Dev` |
| `Explore: Dev_Library` | domain first | `_` | `Library` | `Dev` |

A consistent form gives `Explore: Library - Dev`.

Both names come from the same rename batch. Both replace a name that started
with `Possible Dev`.

## What did not change

The GraphQL schema matches the repo. A live introspection on 2026-09-09
confirmed each item below.

- `UserList` supplies `id`, `name`, `slug`, `description` and `isPrivate`.
  `github/schema.py` reads these five fields.
- `User.lists` returns `UserListConnection` with `nodes` and `pageInfo`.
- The four mutations exist under the names the client calls:
  `createUserList`, `updateUserList`, `deleteUserList` and
  `updateUserListsForItem`.
- `CreateUserListPayload` and `UpdateUserListPayload` both return `list`.
  `DeleteUserListPayload` returns no List identity.

`UserList` also supplies `createdAt`, `lastAddedAt`, `updatedAt` and `user`.
The repo reads none of these four fields.

`UpdateUserListsForItemInput` also accepts `suggestedListIds`. `User` also
supplies `suggestedListNames`. The repo uses neither field.

## Decision (2026-09-09)

The Category stays one flat value. The repo does not add a hierarchy.

An earlier decision on the same day chose a parent-child hierarchy. Evidence
from the Star data reversed that decision. This section keeps the reversal
visible, so that a later reader does not repeat the analysis.

### Why the hierarchy failed

A study of the 1,421 unclassified Stars tested a second axis, the domain of
use. The axis did not hold.

- `Dev` matches about 36 percent of the library. An axis that almost every
  Star shares gives no filtering power.
- The axis that does separate the Stars is the technology, for example Go,
  Python, Ansible or Neovim. That axis is open and high in cardinality. It is
  a tag set, not a hierarchy level.
- Companion code carries no domain of use. Companion code is the largest
  single group, at 187 Stars from one publisher.
- Each of the user's Lists holds one axis, never two. `Explore: Tool` groups
  by subject. `AI Agents Reference` groups by domain.
- Seven Stars already belong to more than one List.
  `NousResearch/hermes-agent` needs two Lists under the hierarchy and under
  the flat model. List membership already carries the second axis.

### What the model becomes

| Item | Decision |
| --- | --- |
| Category | One flat value. `List.category` stays `str \| None`. |
| Second axis | List membership. A Star belongs to more than one List. |
| Intent values | `Explore`, `Current`, `Retired`, `Reference` and `Learn`. |
| `Learn` | A fifth Intent. It has no lifecycle, the same as `Reference`. |
| Absent Intent prefix | The List takes the `Reference` Intent. The whole name becomes the Category. |
| Category values | A kind, such as `Tool`, or a subject, such as `AI Agents`. |
| Vocabulary | The `[taxonomy]` table in `ghstars.toml`. ADR 0009 puts it in the core tier. |
| Unknown Category | Kept and flagged `malformed`. Never rejected. |
| Normalization | The derived Category only. `List.name` keeps GitHub's value. |
| `General` | A reserved Category value. `Explore: General` is the triage inbox. |
| Companion code | The Category `Example`, with the `Reference` or `Learn` Intent. |
| Lifecycle rule | Changed. Exclusivity moves from the Category to the Star. |
| Conflict handling | `tag` refuses the tag. `tag` removes no membership. |
| State migration | None. The stored shape does not change. |

The repo derives the Intent and the Category from the List name at
synchronization time. A name change on GitHub is therefore the migration.

The normalization steps are: change each underscore to a space, collapse each
run of whitespace to one space, then remove the leading and trailing
whitespace. The underscore stands for a space inside one token.

### The lifecycle rule is stricter than the released code

A Star holds at most one lifecycle Intent across all of its Lists. Today
`strip_lifecycle_siblings` applies the rule per Category, so it permits
`Current: Tool` beside `Explore: AI Agents`. That pair is wrong.

ADR 0005 first raised this objection against List membership. The objection is
half correct. The answer is a stricter invariant, not a second Category axis.

All seven of the account's multi-List Stars stay legal under the stricter
rule.

## New invariant to add

A Star must not belong to the triage inbox and to a classified List at the
same time. `Explore: General` means that the subject is undecided.

Three Stars break this rule today: `can1357/oh-my-pi`,
`tiangolo/library-skills` and `mitsuhiko/agent-stuff`. Add the rule to
`verify`.

## Decision — the `Tool` Lists stay (2026-09-09)

Do not change `Explore: Tool - Dev` or `Explore: Tool - CLI` on GitHub now.
Run no mutation. Both Lists classify as a malformed Category until the user
decides.

Do the List surgery later, during the pass that triages the 1,421 unclassified
Stars. A List deletion is irreversible, so it must not happen before the model
ships.

## Work to do

Every design question is decided. ADR 0005 holds the decision. `CONTEXT.md`
holds the terms. `spec.md` holds the stories.

Ship the code before the synchronization. The local store holds the old names,
and a synchronization under today's parser loses the `ML Research` Category
until the code lands.

Items 1 to 7 landed on 2026-09-09. Item 8 waits for the user.

`ghstars status` under-reports until item 8 runs. `lists.json` still holds
`intent = null` and `category = null` for every bare name, because the older
parser wrote it. The triage-inbox check and the lifecycle check cannot see
those Lists until a synchronization rewrites the file.

1. `core/models.py` — add `Learn` to the `Intent` literal.
2. `core/taxonomy.py` — add the normalization steps, the missing-prefix rule
   and the vocabulary check. Move `strip_lifecycle_siblings` from Category
   scope to Star scope.
3. `core/config.py` — add the `[taxonomy]` table to `CoreConfig`, beside
   `[export]`. Ship the default vocabulary as the model default, so that a
   missing file still works.
4. `core/tagging.py` — refuse a tag that breaks the lifecycle rule. Name the
   List that conflicts. Remove no membership.
5. `verify` — add two checks: an unblessed Category, and a Star that sits in
   the triage inbox beside a classified List.
6. `core/fake_client.py` — correct the slug algorithm. See Finding 6.
7. Review every test that expects a silent lifecycle strip.
8. Synchronize. Six List names then flag as malformed. That set is the triage
   worklist.

## Done, 2026-09-09

The six drifted names were resolved on the live account. `Tool - Dev` and
`Tool - CLI` were blessed rather than merged. `Explore: Dev_Library` became
`Explore: Library` via `ghstars category rename`, and `Learning` became
`Learn: General` via `update_list()`. Four Stars were untagged out of the
triage inbox, and the six missing blessed Categories were created --
`Course` and `Example` under `Reference`, the rest under `Explore`.
`ghstars doctor` reports `ok`.

# Pending

Everything still open across this work, in one place. Ticket 35 was folded
in here on 2026-09-09; it holds nothing this section does not.

## Resolved, 2026-09-09

**P1 — `remote bootstrap` versus the explicit-target contract.** Decided:
`--category` stays optional. Omitting it is not a wildcard target, because
`bootstrap`'s plan is derived from `[taxonomy]`, a local, reviewable file --
not from a live filter or search against GitHub, which is what Scope 4's
rule guards against.

The gap was the confirmation order, not the target selection: `--yes` was
checked before the plan existed, so a caller learned what was created only
after the mutation. Fixed to match `unstar`'s bulk contract --
`bootstrap` now computes the plan first and, without `--yes`, fails before
mutating anything and lists every planned target (`Targets: Explore: Tool,
Explore: Library`). `--yes` bypasses that listing for a non-interactive
caller, same as everywhere else in the CLI.

Changed: `src/ghstars/cli/commands/remote.py` (`bootstrap_cmd`),
`docs/reference/cli.md`.

**P2 — Existing semantic duplicate Lists. Resolved, split into ticket
36, 2026-09-09.** The "repair policy" question this item posed --
which List survives, whether membership merges -- turned out not to need
a separate decision. `doctor` already has a rule for exactly this shape of
problem (*unblessed*, *two lifecycle Intents*): when two-or-more repairs
are valid, ghstars reports prose and lets the human choose (ticket 03).
Ticket 36 applied that same rule to `semantic_duplicate` rather than
inventing a new one. Landed: `PROBLEM_SEMANTIC_DUPLICATE` in
`core/doctor.py`, TDD, full test suite and `mise run check` green. No
further decision is pending -- there is no merge/delete command to design
a policy for yet, and prose-only was never meant to be temporary.

## Needs a product decision (1)

**P4 — Stale classification: detect or eliminate.**
`stale_classification_warning` only finds a List with `intent=None` and
`malformed=False`. It misses an un-normalized Category, old whitespace, and
a `Learn:` List the old parser marked malformed.

Two fixes, and they differ in kind. *Detect*: compare the stored
`intent`/`category`/`malformed` against `classify_list(lst)`; complete, but
the duplication stays and so does the class. *Eliminate*: these three fields
are a pure function of `List.name` stored in the same record, so deriving
them on access (a pydantic `computed_field`) makes the staleness class
unreachable and removes `classify_list` and its seven defensive call sites.

Measured on 2026-09-09: eliminating costs 4 failing tests out of 524, all
records whose stored value contradicted the name. `StateStore` stays a dumb
container either way -- the derivation belongs on the model, not the store.

## Ready to build, no decision needed (1)

**P5 — Membership symmetry is unguarded.** `verify_state` checks duplicate
ids and dangling references, but never that `full_name in lst.items` agrees
with `lst.id in star.list_ids`. Those are the two stored sides of one
relationship, and `reconcile_list_membership` is the only thing keeping them
in step. This is the duplication that cannot be collapsed -- the source is a
network fetch, and `tag`/`untag` legitimately write both sides between syncs
-- so it earns a check rather than a redesign.

## Riding with ticket 14 (3)

**P3 — `bootstrap` cannot bind to a reviewed plan. Decided, 2026-09-09:**
a content fingerprint, not a wall-clock cutoff. `doctor --json` gains
`plan_id`, a hash over `sorted(lst.id for lst in lists)` plus
`missing_categories` from that fetch -- it changes if and only if a List
was created, deleted, or renamed into or out of the missing set.
`bootstrap` takes an optional `--plan PLAN_ID`; it already re-fetches and
re-diagnoses right before writing, so it recomputes the same fingerprint
from that fresh fetch and compares. A mismatch refuses with a new
`plan_drift` error code, modeled on the existing
`CODE_LIST_MEMBERSHIP_DRIFT` (`tag`/`untag`) -- same fix: re-run `doctor`,
get a new `plan_id`, retry.

Rejected: a wall-clock cutoff (e.g. "under 30 minutes old"). It proxies for
account change instead of detecting it -- false positive on a quiet
account past the cutoff, false negative on fast drift inside it. The
fingerprint has neither failure mode.

`--plan` stays optional. An interactive human typing `bootstrap` right
after `doctor` still works unflagged -- the in-process race is already
seconds-wide. `--plan` matters for a caller that reads `doctor --json` and
acts later, which is exactly ticket 14's skill layer, so this lands with
that ticket rather than before it. Recorded there as its own acceptance
item, not folded into the generic `bootstrap` line.

**P6 — Typed repairs.** `ListProblem.repairs` and `StarProblem.repairs` are
untyped strings mixing executable commands with prose. `problem` already
discriminates them, so a machine caller can branch today, but the entries
themselves carry no marker. Type them `{kind: "command" | "prose", text}`.

**P7 — Structured partial-bootstrap data.** `PartialBootstrapError` carries
the created names inside an English message rather than as data.

Both change the contract ticket 14's skill consumes, so they land with that
skill, not before it. Ticket 14's scope now names them.

## Larger work, tracked elsewhere

- **Ticket 14** -- the agent skill. Not started, and the largest open item.
- **Ticket 34** -- the skill-layer wizard, plus whether a skill may write
  `ghstars.toml` the way the TUI now does.
- **The triage pass** -- 1,426 unclassified Stars. It needs a method, not a
  command: ghstars must never guess an Intent or a Category (ticket 03).

## Comments

The tracker convention in `docs/agents/issue-tracker.md` referred to a missing
`triage-labels.md`. That file now exists. It maps the `triage` skill's canonical
roles to the strings this tracker uses, and it records why `retired` replaces
`wontfix` and why `done` has no canonical role.
