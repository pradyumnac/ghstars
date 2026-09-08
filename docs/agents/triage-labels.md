# Triage labels

`docs/agents/issue-tracker.md` records triage state on a `Status:` line in each
issue file. This file gives the permitted strings.

The `triage` skill defines canonical role names. This tracker is local Markdown,
not GitHub, so two strings differ from the canonical set. Use the strings in the
"This tracker" column. Never use a string that is not in a table below.

## Where a label goes

Put the state role on a bold `**Status:**` line near the top of the issue file.
Add a dash and a short note when the note helps a later reader.

```markdown
**Status:** ready-for-agent

**Status:** done — all five scopes landed on `main`.
```

## State roles

One issue carries exactly one state role.

| Canonical role | This tracker | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | A maintainer must evaluate the issue. |
| `needs-info` | `needs-info` | The issue waits for more information. |
| `ready-for-agent` | `ready-for-agent` | The issue is fully specified. An agent can start. |
| `ready-for-human` | `ready-for-human` | A person must do the work. |
| `wontfix` | `retired` | The team will not do the work. |
| — | `done` | The work is complete and on `main`. |

### Why two strings differ

`retired` replaces `wontfix`. The repository already used `retired` before this
file existed, on issues 12, 18, 24, 25 and 26. Keep the existing string.

`done` has no canonical role. A GitHub issue closes, and a Markdown file does
not. A local tracker therefore needs a string for finished work.

## Category roles

One issue carries at most one category role. Put it on a bold `**Kind:**` line.

| Canonical role | This tracker | Meaning |
| --- | --- | --- |
| `bug` | `bug` | Something is broken. |
| `enhancement` | `enhancement` | A new feature, or an improvement. |

Use `Kind`, not `Category` and not `Type`:

- `Category` names a ghstars domain concept. See `CONTEXT.md`.
- `Type` marks a wayfinder ticket. See the next section.

The existing issues carry no `Kind:` line. Add one when you next triage an
issue. Do not backfill the whole directory.

## Wayfinder tickets are different

A wayfinder child ticket also holds a `Status:` line, with different values:
`claimed` or `resolved`. A `Type:` line marks such a ticket, with the value
`research`, `prototype`, `grilling` or `task`.

Read the `Type:` line first. A ticket with a `Type:` line uses the wayfinder
values. A ticket without one uses the state roles above.

## Transitions

An untriaged issue goes to `needs-triage` first. From `needs-triage` it moves to
`needs-info`, `ready-for-agent`, `ready-for-human` or `retired`. `needs-info`
returns to `needs-triage` when the reporter answers. `ready-for-agent` and
`ready-for-human` move to `done` when the work lands on `main`.

A maintainer can override any transition. Report an unusual transition, and ask
before you apply it.
