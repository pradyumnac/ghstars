"""List name to Intent/Category taxonomy parsing.

Convention: `{Intent}: {Category}` for
Explore/Current/Retired/Reference/Learn. An unprefixed name takes the
`Reference` Intent, with the whole name as its Category (ADR 0005); only
a malformed name (wrong case, separator, or unknown prefix before `: `)
gets no Intent -- flag it for the user, never guess one (ticket 03).

The derived Category is normalized (underscore -> space, whitespace
collapsed); `List.name` itself is never rewritten. An unblessed Category
is a separate, verify-reported condition from `malformed` -- see
`ghstars.core.status.verify_state`.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from ghstars.core.models import Intent, List

_INTENTS: tuple[Intent, ...] = (
    "Explore",
    "Current",
    "Retired",
    "Reference",
    "Learn",
)

# Lifecycle Lists are mutually exclusive per Category. Reference and Learn are exempt.
LIFECYCLE_INTENTS: frozenset[Intent] = frozenset({"Explore", "Current", "Retired"})

# A name with no Intent prefix means this, rather than "outside the taxonomy".
DEFAULT_INTENT: Intent = "Reference"

# The Category that means "Intent known, subject undecided" -- the triage inbox.
TRIAGE_CATEGORY = "General"

DEFAULT_CATEGORIES: frozenset[str] = frozenset(
    {
        # Kinds -- what a Star is.
        "Tool",
        "Library",
        "Example",
        "Config",
        "App",
        "Course",
        "Skills",
        "Agent",
        "List",
        # Subjects -- what a Star is about.
        "AI Agents",
        "ML Research",
        # Reserved.
        TRIAGE_CATEGORY,
    }
)

_SEPARATOR = ": "
_LEADING_WORD = re.compile(r"^[A-Za-z]+")
_INTENTS_CASEFOLDED = {intent.casefold() for intent in _INTENTS}
# A colon or dash marks a separator attempt; plain whitespace does not.
_SEPARATOR_ATTEMPT = re.compile(r"^\s*[-:]")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ParsedListName:
    intent: Intent | None
    category: str | None
    malformed: bool


_MALFORMED = ParsedListName(intent=None, category=None, malformed=True)


def normalize_category(text: str) -> str:
    """Normalize a Category label: underscore -> space, collapse whitespace.

    Applies to the *derived* Category only; `List.name` is never rewritten
    (ADR 0001).
    """
    return _WHITESPACE.sub(" ", text.replace("_", " ")).strip()


def has_intent_prefix(name: str) -> bool:
    """True when `name` literally starts with an Intent prefix.

    A bare name still parses to `Reference` (ADR 0005), so a renderer
    needs this to avoid showing a prefix GitHub's name doesn't have.
    """
    return any(name.startswith(f"{intent}{_SEPARATOR}") for intent in _INTENTS)


def blessed_categories(categories: Iterable[str]) -> frozenset[str]:
    """Normalize a configured vocabulary so either spelling
    (`AI_Agents` or `AI Agents`) matches.
    """
    return frozenset(normalize_category(item) for item in categories)


def parse_list_name(name: str) -> ParsedListName:
    """Parse a List's `name` per the `{Intent}: {Category}` convention."""
    for intent in _INTENTS:
        prefix = f"{intent}{_SEPARATOR}"
        if name.startswith(prefix):
            category = normalize_category(name[len(prefix) :])
            # `Explore: ` attempts the pattern and yields no subject.
            return (
                ParsedListName(intent=intent, category=category, malformed=False)
                if category
                else _MALFORMED
            )

    leading_word = _LEADING_WORD.match(name)
    if leading_word is not None:
        candidate = leading_word.group(0)
        rest = name[leading_word.end() :]
        if candidate.casefold() in _INTENTS_CASEFOLDED and _SEPARATOR_ATTEMPT.match(
            rest
        ):
            # Reject wrong-case or wrong-separator lifecycle prefixes.
            return _MALFORMED

    if _SEPARATOR in name:
        # Treat an unknown prefix before `: ` as malformed.
        return _MALFORMED

    category = normalize_category(name)
    return (
        ParsedListName(intent=DEFAULT_INTENT, category=category, malformed=False)
        if category
        else _MALFORMED
    )


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
    at a time. `Reference` and `Learn` Lists are exempt -- never a strip
    candidate, and `target` itself is a no-op source when it is not a
    lifecycle List.

    Stays per-Category on purpose (ADR 0005): a per-Star scope would
    delete the membership holding a Star's second subject, so `verify`
    reports two lifecycle Intents instead of any write path stripping one.

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
