# Local state and membership dataflow

## GitHub holds the truth

GitHub is the sole source of truth for List existence and membership
(ADR 0001). Two local files mirror GitHub. They exist so that a read
command answers without a network call.

| File | Holds |
| --- | --- |
| `stars.json` | every `Star` record, including `Star.list_ids` |
| `lists.json` | every `List` record, including `List.items` |

## One relationship, two stored sides

`Star.list_ids` and `List.items` describe one many-to-many relationship
from opposite ends. A Star belongs to many Lists. A List holds many
Stars.

GitHub returns one direction only. A Lists fetch returns each List with
its `items`. No fetch returns the Lists of one Star. `sync()` therefore
calls `reconcile_list_membership()`, which derives every
`Star.list_ids` value from `List.items`.

| Field | Origin | Written by |
| --- | --- | --- |
| `List.items` | fetched from GitHub | `sync`, `tag`, `untag`, `unstar` |
| `Star.list_ids` | derived from `List.items` | the same four commands |

Neither field is a computed view of the other in code. The relationship
lives on GitHub, so the local code must keep both sides in step.

## Dataflow

```
                      GITHUB  (source of truth, ADR 0001)
                                  |
        +-------------------------+-------------------------+
        |                         |                         |
     sync()               tag_star() / untag_star()    unstar_star()
                                  |                         |
  fetch_stars()            push the mutation          remove_star()
  fetch_lists()            to GitHub first            to GitHub first
        |                         |                         |
        v                         v                         v
  reconcile_list_          compute the new ids       archive_star()
  membership()             in memory                 remove_star_
  derives list_ids                                   from_lists()
  from List.items
        |                         |                         |
        +-------------------------+-------------------------+
                                  |
                      with store.lock():        <- one lock
                          save_stars(...)       <- write 1, atomic
                          save_lists(...)       <- write 2, atomic
                                  |
        +-------------------------+-------------------------+
        v                                                   v
   stars.json                                          lists.json
   Star.list_ids                                       List.items
```

Every write path ends with the same two calls. Each call writes one
file atomically. The two calls together are not one transaction.

## Where the two sides can disagree

The lock stops a second ghstars process from writing between the two
calls. The lock does not protect a process that stops between them.

1. **A process stops between the two writes.** A signal, an
   out-of-memory kill, or a power loss can stop it. One file then holds
   the new state, and the other file holds the old state.
2. **A person edits one file by hand.** A repair by hand, or a
   migration script, can change one file and leave the other.
3. **New code writes one side only.** No test guards this today, so
   such a change reaches users without a warning.

## Structural checks

`verify_state()` reads both files. It returns a list of problem
strings. `ghstars status` reports the result as `verify_ok` and
`verify_problems`. An empty list means `verify_ok` is `true`.

| # | Check | Catches |
| --- | --- | --- |
| 1 | No duplicate `Star.full_name` | `stars.json` written by something other than a clean sync |
| 2 | No duplicate `List.id` | `lists.json` written the same way |
| 3 | No `Star.list_ids` entry naming an absent `List.id` | a membership that points at nothing |
| 4 | A Star and a List that both exist agree about membership | the three cases above (ticket 33 P5, landed 2026-09-09) |

Check 3 catches a reference to a List that `lists.json` does not hold.
Check 4 catches a reference to a List that `lists.json` does hold and
that does not name the Star back.

Check 4 does not flag a `List.items` entry that names a Star absent
from `stars.json`. `sync()` fetches Stars and Lists in two separate
calls, so that state is expected, and it self-heals at the next sync.
Read `known-limitations.md` for that race.

## Reading needs the same discipline as writing

`build_status()` reads both files to run check 4. A reader that loads
one file, releases the lock, then loads the other can read a moment a
writer left half-applied -- the same gap a writer avoids by holding one
lock across both of its writes. `build_status()` now holds one lock
across every `load_*` call, for the same reason.

## Recovery

Run `ghstars sync`. Sync fetches `List.items` from GitHub again and
derives every `Star.list_ids` value from it. One sync repairs each
disagreement on this page.
