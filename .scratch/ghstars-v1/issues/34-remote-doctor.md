# 34 — `ghstars doctor`: diagnose and bootstrap a remote

**What to build:** A command that checks a GitHub account against this repo's
taxonomy rules, reports a repair plan, and creates the Lists a blessed
Category is missing. The skill layer reads the plan and walks the user
through it.

**Status:** ready-for-human — the command landed on 2026-09-09, and its Star-
level check plus `ghstars untag` landed the same day. The skill-layer wizard
is not built.

**Kind:** enhancement

**Blocked by:** None. Ticket 33 landed the rules this command checks.

## Delivered on 2026-09-09

- [x] `ghstars doctor` reads live Lists and reports every name that needs
      attention, with the valid repairs for each.
- [x] Two conditions are reported apart, because their repairs differ:
      `malformed` (bad shape, one repair) and `unblessed` (good shape,
      unblessed Category, two repairs).
- [x] `remote bootstrap --yes --intent <Intent>` creates one List per blessed
      Category that has no List. It never renames and never deletes.
- [x] `remote bootstrap` refuses without `--intent`. ghstars does not guess
      an Intent (ticket 03).
- [x] A name that needs attention blocks `remote bootstrap`. `--force`
      overrides it.
- [x] `--json` emits a `DoctorReport`, not a `FIELD_REGISTRY` field set, so
      the CLI field sets keep their ticket 14 contract.
- [x] No prompt anywhere. Ticket 30 Scope 0 requires the command to work
      without a terminal.
- [x] `doctor` exits 0 whenever the diagnosis itself succeeded. ADR 0010
      reserves a non-zero exit for a failure carrying an error envelope, and
      a report is not one. Callers branch on `ok`.
- [x] `ok` covers defects only. A blessed Category with no List is an
      opportunity, not a defect; folding it in left `ok` false forever.
- [x] One rule function (`taxonomy.star_conflicts`) backs both `verify_state`
      (local state) and `doctor` (live state), so the two reporters cannot
      check unequal rule sets.

## Why the names gate the creates

A rename can turn an unblessed Category into a blessed one. That removes the
need to create a List for it. Creating first would therefore make Lists the
user does not want.

## Command shape, settled 2026-09-09

`doctor` is read-only. Every repair is its own verb, named for what it fixes.

| Problem | Repairs | Verb |
| --- | --- | --- |
| Blessed Category with no List | one | `remote bootstrap` |
| Star in the triage inbox and a classified List | one | `untag` |
| Malformed name | one (rename) | `remote rename-list` |
| Unblessed Category | two (bless or rename) | none -- prose only |

A repair becomes a command only when the repair *type* is deterministic. Two
valid repair types means prose, because ghstars must not choose (ticket 03).

`remote` holds administrative, List-shaped writes. `tag`, `untag` and
`unstar` stay top-level: they act on one Star's membership, not on List
structure. `category rename`/`drain` stay where they are -- renaming a
shipped command buys nothing today.

Blessing a Category never becomes a command. ADR 0002 forbids ghstars writing
to `config/` on the user's behalf, so it stays a hand edit of `ghstars.toml`.

`remote rename-list` closes the gap found renaming `Learning` to
`Learn: General` by hand: `category rename` keeps each List's Intent, so it
cannot move a List between Intents.

## Not built

The interactive wizard. It belongs to the skill layer, not to the CLI, because
a prompt inside `ghstars` breaks the Scope 0 contract that the agent skill
depends on. The skill reads `doctor --json`, asks the user per Category, then
calls back with explicit flags.

Design questions for that work:

1. Decide whether the wizard offers a rename for each malformed name, or only
   reports it. A rename is a live mutation.
2. Decide how the wizard chooses an Intent per Category. One Intent for the
   whole run is the current shape of `--intent`.
3. Decide whether the wizard blesses a word in `ghstars.toml` on the user's
   behalf. ADR 0002 forbids ghstars writing there; a skill is not ghstars, so
   this needs a ruling.

## Comments

Verified against the live account on 2026-09-09, read-only. It reported four
names needing attention and seven blessed Categories with no List, and it
blocked the create phase as designed. No mutation ran.
