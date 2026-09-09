# 36 — `doctor`: detect semantic duplicate Lists

**What to build:** A fifth `doctor` condition. Two Lists that parse to the
same `(intent, category)` are a semantic duplicate -- `rename_list` already
stops a *new* one from being created, but nothing reports a pair that
already exists on GitHub, and `tag`'s `_find_list` silently binds to
whichever one GitHub returns first.

**Status:** ready-for-human -- landed 2026-09-09. TDD: failing tests
written first (`tests/test_doctor.py`), confirmed red, then implemented.
Full suite (542 tests), `ruff format`, `ruff check`, and `mypy` all pass.

**Kind:** enhancement

**Blocked by:** None. **Blocks ticket 33** -- P2 in ticket 33's "Pending"
section names this gap; this ticket is that item, split out because the
repair-policy half stays undecided while detection does not.

## Origin

Split out of ticket 33 P2 on 2026-09-09. Full detection design (rule table,
scope boundary, worked examples) lives in ticket 33's P2 entry and is
reproduced here as the spec for this ticket's build.

## Detection rule

Group every non-malformed classified List by `(intent, category)`. Any
group with more than one List is a `semantic_duplicate`.

`normalize_category` already folds the underscore-vs-space and
whitespace-run cases into one `category` value (Findings 2 and 3 in ticket
33) -- grouping by the existing `(intent, category)` fields catches those
for free. The only new fold this ticket adds is case:

| Element | System prefers (canonical) | System also accepts (folds to canonical) | Source |
| --- | --- | --- | --- |
| Word separator | Space | Underscore `_` | Already folded by `normalize_category` |
| Whitespace | One space | Any run (double space, leading/trailing) | Already folded by `normalize_category` |
| Case | Exactly as spelled in `[taxonomy]` (Title Case) | Any case, folded case-insensitively for grouping only | New this ticket |
| Intent prefix | Explicit `{Intent}: ` | Absent -- defaults to `Reference` | Already handled by `parse_list_name` (ADR 0005) |
| Sub-Category separator ` - ` | -- never folded -- | -- never folded -- | Finding 1: a genuinely different Category, confirmed fine, out of scope |

Case-folding is scoped to this check's grouping key only. It does not
change `check_writable_list_name` or `blessed_categories` -- widening
case-insensitivity to blessed-Category matching generally is a separate,
undecided question; do not fold it into this ticket.

## Repair

Prose only, same rule as *unblessed* and *two lifecycle Intents*: two-or-more
valid repairs (which List survives, whether membership merges) means
ghstars must not choose (ticket 03). Name the List whose `category` is an
exact (case-sensitive) match for a blessed vocabulary entry, if one exists
in the group, as a hint -- never a forced choice.

No merge/delete command exists yet (`GitHubClient.delete_list` has no CLI
verb), so there is nothing to offer as a command either way.

## Acceptance

- [x] `PROBLEM_SEMANTIC_DUPLICATE` constant in `core/doctor.py`.
- [x] `diagnose()` reports one `ListProblem` per List in a duplicate group,
      `detail` naming the other List(s) in the group.
- [x] Case-only differences are flagged (new).
- [x] Underscore/whitespace differences are flagged (already covered by
      existing normalization; regression test added).
- [x] The ` - ` sub-Category separator is never flagged as a duplicate
      (Finding 1 boundary; regression test added).
- [x] A List already matching the blessed spelling exactly is named as a
      hint in `detail` when one exists in the group.
- [x] `repairs` is prose only, never a command.
- [x] `create_blocked` covers this condition the same way it already covers
      `malformed`/`unblessed` (no new logic needed -- `bool(problems)`).
- [x] `docs/reference/cli.md`'s `doctor` conditions table gets a fifth row.
- [x] Ticket 33 P2 updated to point here.

## Comments

TDD: 7 tests written first in `tests/test_doctor.py`, confirmed red
(`test_diagnose_flags_two_lists_with_the_same_parsed_identity`,
`test_diagnose_folds_underscore_and_whitespace_for_duplicate_detection`,
`test_diagnose_folds_case_for_duplicate_detection`,
`test_diagnose_names_the_blessed_spelling_as_a_hint`,
`test_diagnose_does_not_fold_the_subcategory_separator`,
`test_semantic_duplicate_repair_is_prose_not_a_command`,
`test_diagnose_does_not_flag_a_lone_list_as_a_duplicate`), then
`_duplicate_problems()` added to `core/doctor.py` and wired into
`diagnose()`. Grouping key is `(lst.intent, lst.category.casefold())` over
non-malformed classified Lists -- underscore/whitespace need no extra
folding because `normalize_category` already collapses them into
`List.category` before this check ever sees the name.
