# Handoff

## Next work

Tickets 33, 34 and 36 landed on 2026-09-09. The taxonomy is flat, the
vocabulary lives in config, and `ghstars doctor` reports the account
against it -- five conditions now, including semantic-duplicate List
detection (ticket 36). See ADR 0005 for the model and
`docs/reference/cli.md` for the repair loop.

`verify_state` (local, offline, used by `ghstars status`) also gained a
fourth structural check the same day: `Star.list_ids` and `List.items`
must agree, in both directions, for any Star/List that both exist
locally (ticket 33 P5). See `docs/explanation/state-dataflow.md` for the
full dataflow this check guards and why the fix touched `build_status`'s
locking, not just `verify_state`.

**Ticket 14, the agent skill, is next and is now the largest open item.** This
session tripled its surface: the skill must cover `doctor`, `remote
bootstrap`, `remote rename-list` and `untag` alongside the commands ticket 30
delivered.

### Open work

**Every open item lives in one place: ticket 33's "Pending" section**
(`.scratch/ghstars-v1/issues/33-list-name-syntax-drift.md`). Read it before
starting anything in this area. Ticket 35 was folded into it; ticket 34 and
ticket 14 point at it rather than repeating it.

Seven items were tracked. Four remain open (P4, P3, P6, P7); P1, P2, and
P5 are resolved. Summarized:

| Ref | Item | State |
| --- | --- | --- |
| P1 | `remote bootstrap` with no `--category` versus the explicit-target rule in `docs/reference/cli.md` | Resolved -- `--category` stays optional; `--yes` now gates on a computed plan, same as `unstar` |
| P2 | Existing semantic duplicate Lists | Resolved -- detection landed as ticket 36; prose-only repair was already the right shape (ticket 03), no separate policy needed |
| P3 | `bootstrap` cannot bind to a reviewed `doctor` plan | Decided -- a `plan_id` content fingerprint, not a wall-clock cutoff; `bootstrap --plan` rides with ticket 14 |
| P4 | Stale classification: detect the drift, or remove the duplication that causes it | Needs a decision |
| P5 | `List.items` and `Star.list_ids` are the two stored sides of one relationship, and nothing checks they agree | Resolved -- `verify_state` gained a 4th check; `build_status`'s locking fixed as a prerequisite |
| P6 | Typed repair entries, replacing untyped strings that mix commands with prose | Rides with ticket 14 |
| P7 | Structured partial-bootstrap data, replacing an English error message | Rides with ticket 14 |

Beyond those: ticket 14's skill, ticket 34's wizard, and the triage pass for
the unclassified Stars. That pass needs a *method*, not a command -- ghstars
must never guess an Intent or a Category (ticket 03).

Ticket 37's offline classification-debt workflow is implemented. The CLI
commands are `ghstars classify extract`, `write`, and `render`. They read only
local pull data, use a runtime work directory, join by exact `owner/name`, and
write a numbered three-column review report. The dedicated harness skill is at
`skills/ghstars-bulk-classify/SKILL.md`. Ticket 14 has a separate stub at
`skills/ghstars/SKILL.md`. The bulk skill keeps Intent as a low-confidence
guess, presents three Category choices, and requires final user approval before
any adoption commands run. The CLI does not apply
proposals.

Committed as `740795a` (`Add offline Star classification workflow`). The
untracked `.scratch/ghstars-v1/triage/` sample data was not committed and was
removed during cleanup. Existing edits in `spec.md` and `CONTEXT.md` remain
uncommitted.

The first clean-context review found trust-boundary defects in ticket 37. The
corrective pass now validates local membership, strict proposal input, snapshot
content, exact proposal keys, atomic work files, Markdown escaping, and JSON
error handling. The ghstars corrective commits are `a55d27e`, `e8d2651`, `9524ea4`, and `06be81c`.
The bulk skill is versioned in this project at
`skills/ghstars-bulk-classify/SKILL.md`, and the Ticket 14 stub is at
`skills/ghstars/SKILL.md`.

### Notes repository split

Resolved 2026-09-09. ghstars does not depend on the old notes path or on
`scripts/gh-stars.py`. The only reference is one historical line in
`core/status.py`'s docstring. The split cannot break this repository.

## Unscheduled follow-ups

No ticket covers these.

- Replace the Layout column text fields with a two-pane chooser.
- Add `h`/`j`/`k`/`l` navigation to TUI `DataTable` widgets without changing
  text-input or modal keys.
- Reproduce the disappearing Star-selection mark in a real terminal. Headless
  tests do not reproduce the problem.

## Safety

- Do not run a real sync without explicit approval.
- Do not run a real unstar or List mutation during development.
- Use an isolated state directory for an approved live test. Set
  `GHSTARS_HOME` to get one.
- Keep normal GitHub authentication separate from test state.

## Checks

Run focused tests, the full test suite, and diagnostics before handoff.

## Task rail

*No unfinished Task tool work.*
