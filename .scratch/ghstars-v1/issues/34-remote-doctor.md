# 34 — `ghstars doctor`: diagnose and bootstrap a remote

**What to build:** A command that checks a GitHub account against this repo's
taxonomy rules, reports a repair plan, and creates the Lists a blessed
Category is missing. The skill layer reads the plan and walks the user
through it.

**Status:** ready-for-human — the command landed on 2026-09-09. The skill-layer
wizard is not built.

**Kind:** enhancement

**Blocked by:** None. Ticket 33 landed the rules this command checks.

## Delivered on 2026-09-09

- [x] `ghstars doctor` reads live Lists and reports every name that needs
      attention, with the valid repairs for each.
- [x] Two conditions are reported apart, because their repairs differ:
      `malformed` (bad shape, one repair) and `unblessed` (good shape,
      unblessed Category, two repairs).
- [x] `--fix --yes --intent <Intent>` creates one List per blessed Category
      that has no List. It never renames and never deletes.
- [x] `--fix` refuses without `--intent`. ghstars does not guess an Intent
      (ticket 03).
- [x] A name that needs attention blocks `--fix`. `--force` overrides it.
- [x] `--json` emits a `DoctorReport`, not a `FIELD_REGISTRY` field set, so
      the CLI field sets keep their ticket 14 contract.
- [x] No prompt anywhere. Ticket 30 Scope 0 requires the command to work
      without a terminal.

## Why the names gate the creates

A rename can turn an unblessed Category into a blessed one. That removes the
need to create a List for it. Creating first would therefore make Lists the
user does not want.

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
