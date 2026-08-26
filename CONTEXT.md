# ghstars

A terminal-first tool (TUI + CLI) for developers to manage and classify their GitHub starred repos into Lists, keeping GitHub itself as the synced backing store.

## Language

**Star**:
A GitHub repository the user has starred. The core entity ghstars organizes.
_Avoid_: Bookmark, Favorite.

**List**:
GitHub's native starred-repo grouping (a `UserList` in GitHub's GraphQL API). The atomic classification container in ghstars — a Star belongs to zero or more Lists. Synced bidirectionally with GitHub via its Lists API (`createUserList`, `updateUserList`, `deleteUserList`, `updateUserListsForItem`).
_Avoid_: Tag, Folder, Bucket.

**Intent**:
A List's stated relationship to its Category, encoded as the prefix of the List's name: `Explore` (candidate, undecided), `Current` (adopted, in use), `Retired` (formerly adopted, no longer in active use), or `Reference` (informational — no adoption question applies). `Explore`, `Current`, and `Retired` are mutually exclusive per Category — a Star sits in exactly one at a time, moving through the lifecycle as its status changes. `Reference` stands alone, no lifecycle. A List with no Intent prefix is a General List, outside this taxonomy entirely.
_Avoid_: Stage, Status, Type.

**Retired** (Intent value):
Marks a Star the user deliberately keeps starred and classified, but no longer actively uses — distinct from unstarring. The star stays visible and discoverable on GitHub; only its Intent changes, out of `Current` into `Retired: {Category}` (or the `Retired: General` catchall). Orthogonal to whether the underlying Star itself is still starred.
_Avoid_: Archived (reserved for the Star-level unstar record, not List Intent — see below).

**Archived** (Star property, not an Intent):
A Star that has been unstarred on GitHub. ghstars keeps its historical record locally (never deleted) but it carries no Intent and no List membership going forward — a different axis entirely from Retired, which keeps the star active and classified.
_Avoid_: Retired (do not conflate the two — Archived means the star itself is gone; Retired means the star stays but its use has ended).

**Category**:
The subject-matter label in a List's name, after the Intent prefix — for example `Vendored Skills` in `Explore: Vendored Skills`. A Category label names a kind of thing (`Dev Tools`, `CLI Tools`) or a subject (`AI`, `DevOps`). The user chooses which. Category is the only name for this slot, under every Intent. General Lists have no Intent prefix, so the whole name is freeform and holds no Category.
_Avoid_: Tag, Topic, Label.

**General List**:
A List with no Intent prefix — freeform, outside the Current/Explore/Reference taxonomy entirely.
_Avoid_: Freeform List, Uncategorized List.

**View Mode**:
The arrangement ghstars uses to put Stars on screen — a flat Star list, a grid, or a Folder. A View Mode changes the arrangement only. It never changes which Stars the user sees — a Filter does that.
_Avoid_: Display, Screen. Do not use Layout for this concept; a Layout is a different thing (see below).

**Layout**:
A named density preset for the Star table, holding columns, row height, detail-pane height, and pane visibility. ghstars ships `compact` and `balanced`. `config/tui.toml` defines presets; `state/tui-state.toml` records the active preset (ADR 0008). A Layout is not a View Mode: a View Mode picks the arrangement, and a Layout tunes the flat table.
_Avoid_: View Mode, Density, Theme.

**Folder**:
A View Mode that shows each List as a container, and the Stars of one List as the contents of that container. The hierarchy is one level deep: a Folder holds Stars, and never another Folder. A Star that belongs to no List falls back to one default Folder.
_Avoid_: Directory, Tree, Group, Bucket.

**Filter**:
A rule that limits which Stars the user sees by Category, Intent, or List. A Filter narrows the current View Mode.
_Avoid_: Query, Search (Search matches free text, and is a separate action).

**TUI configuration editor**:
A form for `config/tui.toml`. Press `g` to open it, or select Edit config
from Ctrl+P. Esc validates and saves. `x` discards. `q` quits only from the
main screen. The form body scrolls under fixed key help.

**Retriage Queue**:
A local-only holding area for a Star whose pending List-membership change conflicted with a concurrent change on GitHub since the last sync. Never synced to GitHub — conflict handling is ghstars' responsibility, not GitHub's.
_Avoid_: Staging list, conflict list.

**Nudge**:
An observation the agent skill records, mid-operation, that some part of ghstars' workflow could be tweaked for better accuracy, easier operation, or token efficiency. Purely observational — never auto-applied. Deduplicated by a stable slug in dedicated files under `runtime/nudges/`, surfaced to the user only on human-facing surfaces (never in `--json`/agent-mode output), and only when explicitly enabled — off by default.
_Avoid_: Suggestion, TODO, hint.
