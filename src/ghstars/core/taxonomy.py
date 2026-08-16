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
_SEPARATOR = ": "
_LEADING_WORD = re.compile(r"^[A-Za-z]+")
_INTENTS_CASEFOLDED = {intent.casefold() for intent in _INTENTS}
# A colon or dash right after the leading word reads as an attempted
# separator. Plain whitespace does not ("Explore Zone" is General, not
# an attempt at "Explore: Zone").
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
            # Case-insensitive word match plus an attempted separator:
            # wrong case or wrong separator, e.g. "explore: Foo" or
            # "Explore - Foo". A bare "Explore" or "Explore Zone" is
            # General, not malformed.
            return ParsedListName(intent=None, category=None, malformed=True)

    if _SEPARATOR in name:
        # `{word}: {rest}` where `word` is not a recognized Intent.
        # Treated as a misspelled prefix, not a General name with a colon.
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
