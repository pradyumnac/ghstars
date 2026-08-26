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
`Explore`, `Current`, `Retired`, or `Reference`. `Explore`, `Current`, and
`Retired` are mutually exclusive per Category. `Reference` has no lifecycle. A
List without an Intent prefix is a General List.
_Avoid_: Stage, Status, Type.

**Retired** (Intent value):
A Star stays starred and classified but is no longer in active use. It moves
from `Current` to `Retired: {Category}` or `Retired: General`.
_Avoid_: Archived.

**Archived** (Star property):
A Star was unstarred on GitHub. ghstars keeps its local history but removes its
Intent and List membership. This is distinct from Retired.
_Avoid_: Retired.

**Category**:
The subject label after a List Intent prefix. For example, `Vendored Skills` in
`Explore: Vendored Skills`. A General List has no Category.
_Avoid_: Tag, Topic, Label.

**General List**:
A List without an Intent prefix. It is outside the Intent taxonomy.
_Avoid_: Freeform List, Uncategorized List.

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

**Nudge**:
An observation that the agent skill records about workflow friction. It never
auto-applies. Files use a stable slug under `runtime/nudges/`. Human surfaces
show Nudges only when enabled. JSON and agent-mode output never show them.
_Avoid_: Suggestion, TODO, hint.
