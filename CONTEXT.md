# ghstars

A terminal-first tool (TUI + CLI) for developers to manage and classify GitHub
Stars into Lists. GitHub remains the synced backing store.

## Language

**Star**:
A GitHub repository the user has starred. ghstars organizes Stars.
_Avoid_: Bookmark, Favorite.

**List**:
GitHub's native starred-repository grouping (`UserList` in GitHub GraphQL). A
Star belongs to zero or more Lists. ghstars syncs Lists bidirectionally through
GitHub's Lists API.
_Avoid_: Tag, Bucket.

**Intent**:
A List's stated relationship to its Category. The List name starts with
`Explore`, `Current`, `Retired`, `Reference`, or `Learn`. A Star holds at most
one of `Explore`, `Current`, and `Retired` across all of its Lists. `Reference`
and `Learn` have no lifecycle and no limit. A List without an Intent prefix has
the `Reference` Intent, so `Course` and `Reference: Course` name one List.
ghstars writes the explicit form. Only a List with a malformed name has no
Intent, because ghstars never guesses one.
_Avoid_: Stage, Status, Type.

**Retired** (Intent value):
A Star stays starred and classified but is no longer in active use. It moves
from `Current` to `Retired: {Category}` or `Retired: General`.
_Avoid_: Archived.

**Learn** (Intent value):
The user keeps a Star to learn from it. `Learn` has no lifecycle. A `Learn`
List can sit beside an `Explore`, `Current`, or `Retired` List on the same
Star.
_Avoid_: Learning, Study, Training.

**Archived** (Star property):
A Star was unstarred on GitHub. ghstars keeps its local history but removes its
Intent and List membership. This is distinct from Retired.
_Avoid_: Retired.

**Category**:
The subject label after a List Intent prefix. For example, `Tool` in
`Explore: Tool`. A Category names a kind of thing, such as `Tool`, or a
subject, such as `AI Agents`. A List without an Intent prefix uses its whole
name as the Category.
_Avoid_: Tag, Topic, Label.

**General** (Category value):
The reserved Category for a List with a known Intent and an undecided subject.
Any `{Intent}: General` List is a triage inbox, `Explore: General` being the
common one. A Star stays there until the user gives it a Category, and must
not sit in an inbox and a classified List at the same time — that claims the
subject is both undecided and decided.
_Avoid_: Misc, Uncategorized, Inbox.

**Example** (Category value):
Sample Code, scripts which serve the user as learning or revising value. May
show recommended design patterns, book accompaniments code repos. An Example List takes
the `Reference` Intent or the `Learn` Intent.
_Avoid_: Book, Sample, Demo code.

**Layout**:
A named density preset for the flat Star table. It controls columns, row height,
Detail pane height, and pane visibility. ghstars ships `compact` and `balanced`.
`config/tui.toml` defines presets. `state/tui-state.toml` records the active
preset.
_Avoid_: View Mode, Density, Theme.

**Filter**:
A rule that limits the Stars in the flat Star table by Category, Intent, or
List.
_Avoid_: Query, Search.

**TUI configuration editor**:
A form for `config/tui.toml`. Press `g` to open it, or select Edit config from
Ctrl+P. Esc validates and saves. `x` discards. `q` quits only from the main
screen. The form body scrolls under fixed key help.

**Retriage Queue**:
A local-only holding area for a Star whose pending List-membership change
conflicted with a GitHub change since the last sync. It never syncs to GitHub.
_Avoid_: Staging list, conflict list.

## CLI field-set stability

`ghstars stars`, `github-lists`, and `retriage`'s `--json` field sets
(`core.fields.FIELD_REGISTRY`) carry no schema version (ADR 0010, Decision
9/18 in ticket 30). A field-set change and the corresponding ticket 14
agent-skill change must land in the same change -- there is no version
negotiation for the skill to fall back on if the two drift apart.

`stars` and `github-lists` were `list` and `lists` until ticket 30 Scope 7
renamed them to resolve a command-name clash (Decision 26) -- the
`FIELD_REGISTRY` keys `"star_row"`/`"list"` and internal Python
identifiers (`--list` Filter option, `List` model, `list_names` field)
were not touched. Those name the domain entity "List", not the command,
and are not ambiguous the way two adjacent bare CLI command names were.
