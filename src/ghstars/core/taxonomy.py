"""List name to Intent/Category taxonomy parsing.

Convention: `{Intent}: {Category}` for Explore/Current/Retired/Reference.
An unprefixed name is valid General (CONTEXT.md), not an error.

A malformed name attempts the Intent-prefix pattern but does not match
it: wrong case (`explore: Foo`), wrong separator (`Explore - Foo`), or
an unrecognized word before `: ` (`Exploring: Foo`). Flag these for the
user to rename. Never guess an Intent.
"""

import re
from dataclasses import dataclass

from ghstars.core.models import Intent, List

_INTENTS: tuple[Intent, ...] = ("Explore", "Current", "Retired", "Reference")

# Lifecycle Lists are mutually exclusive per Category; Reference and General Lists are exempt.
LIFECYCLE_INTENTS: frozenset[Intent] = frozenset({"Explore", "Current", "Retired"})

_SEPARATOR = ": "
_LEADING_WORD = re.compile(r"^[A-Za-z]+")
_INTENTS_CASEFOLDED = {intent.casefold() for intent in _INTENTS}
# A colon or dash marks a separator attempt; plain whitespace does not.
_SEPARATOR_ATTEMPT = re.compile(r"^\s*[-:]")


@dataclass(frozen=True)
class ParsedListName:
    intent: Intent | None
    category: str | None
    malformed: bool


def parse_list_name(name: str) -> ParsedListName:
    """Parse a List's `name` per the `{Intent}: {Category}` convention."""
    for intent in _INTENTS:
        prefix = f"{intent}{_SEPARATOR}"
        if name.startswith(prefix):
            return ParsedListName(
                intent=intent, category=name[len(prefix) :], malformed=False
            )

    leading_word = _LEADING_WORD.match(name)
    if leading_word is not None:
        candidate = leading_word.group(0)
        rest = name[leading_word.end() :]
        if candidate.casefold() in _INTENTS_CASEFOLDED and _SEPARATOR_ATTEMPT.match(
            rest
        ):
            # Reject wrong-case or wrong-separator lifecycle prefixes.
            return ParsedListName(intent=None, category=None, malformed=True)

    if _SEPARATOR in name:
        # Treat an unknown prefix before `: ` as malformed.
        return ParsedListName(intent=None, category=None, malformed=True)

    return ParsedListName(intent=None, category=None, malformed=False)


def classify_list(lst: List) -> List:
    """Return `lst` with intent/category/malformed derived from its name."""
    parsed = parse_list_name(lst.name)
    return lst.model_copy(
        update={
            "intent": parsed.intent,
            "category": parsed.category,
            "malformed": parsed.malformed,
        }
    )


def strip_lifecycle_siblings(
    list_ids: list[str], *, lists: list[List], target: List
) -> tuple[list[str], list[str]]:
    """Remove any sibling List id sharing `target`'s Category but a
    different lifecycle Intent (Explore/Current/Retired) from `list_ids`.

    This is the mutual-exclusivity invariant (spec story 16, CONTEXT.md):
    a Star sits in at most one of Explore/Current/Retired per Category
    at a time. Reference and General (`intent=None`) Lists are exempt --
    never a strip candidate, and `target` itself is a no-op source when
    it is not a lifecycle List.

    Returns `(new_ids, removed_ids)`. `removed_ids` is empty when
    `target`'s intent is not lifecycle, or no sibling was present in
    `list_ids`.

    Shared by `ghstars.core.tagging.tag_star` (the original site of this
    check, ticket 17) and `ghstars.core.category.drain_category` (ticket
    07) -- any write path that sets a Star's final List membership needs
    this same invariant, not a re-derived copy (per ticket 17's
    post-implementation note on generalizing it later).
    """
    if target.intent not in LIFECYCLE_INTENTS:
        return list_ids, []
    sibling_ids = {
        item.id
        for item in lists
        if item.category == target.category
        and item.intent in LIFECYCLE_INTENTS
        and item.intent != target.intent
    }
    removed = [i for i in list_ids if i in sibling_ids]
    if not removed:
        return list_ids, []
    return [i for i in list_ids if i not in sibling_ids], removed
