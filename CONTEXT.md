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
The subject-matter label in a List's name, following the Intent prefix — e.g. `Vendored Skills` in `Explore: Vendored Skills`. General Lists have no Intent prefix, so their whole name is freeform, not a Category in this sense.
_Avoid_: Tag, Topic (except within Reference Lists, where "Topic" names the informational subject — e.g. `Reference: AI Agents`).

**General List**:
A List with no Intent prefix — freeform, outside the Current/Explore/Reference taxonomy entirely.
_Avoid_: Freeform List, Uncategorized List.

**Retriage Queue**:
A local-only holding area for a Star whose pending List-membership change conflicted with a concurrent change on GitHub since the last sync. Never synced to GitHub — conflict handling is ghstars' responsibility, not GitHub's.
_Avoid_: Staging list, conflict list.

**Nudge**:
An observation the agent skill records, mid-operation, that some part of ghstars' workflow could be tweaked for better accuracy, easier operation, or token efficiency. Purely observational — never auto-applied. Deduplicated by a stable slug in dedicated files under `runtime/nudges/`, surfaced to the user only on human-facing surfaces (never in `--json`/agent-mode output), and only when explicitly enabled — off by default.
_Avoid_: Suggestion, TODO, hint.
