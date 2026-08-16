"""List name -> Intent/Category taxonomy parsing.

Naming convention (spec.md "Naming convention & validation"): `{Intent}: {Category}`
for Explore/Current/Retired/Reference; an unprefixed name is a **valid** General
List (CONTEXT.md's own definition -- "a List with no Intent prefix ... outside
the taxonomy entirely", a first-class category, not an error).

"Malformed" is reserved for names that look like they're *attempting* the
Intent-prefix pattern but don't exactly match it: wrong case (`explore: Foo`),
wrong separator (`Explore - Foo`), or an unrecognized word before a `: `
separator (`Exploring: Foo`). Those are flagged for the user to rename, never
silently guessed at. See ticket 03's Comments for the doc inconsistency this
resolves between spec.md and CONTEXT.md, and the tradeoff this rule accepts.
"""

import re
from dataclasses import dataclass

from ghstars.core.models import Intent, List

_INTENTS: tuple[Intent, ...] = ("Explore", "Current", "Retired", "Reference")
_SEPARATOR = ": "
_LEADING_WORD = re.compile(r"^[A-Za-z]+")
_INTENTS_CASEFOLDED = {intent.casefold() for intent in _INTENTS}
# Whatever follows the leading word, once it's optional whitespace then a
# colon or dash, reads as an attempted separator -- as opposed to plain
# whitespace-then-another-word, which is just a normal multi-word name
# (e.g. "Explore Zone" is General, not an attempt at "Explore: Zone").
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
            # Right word (case-insensitively), and what follows it looks
            # like an attempted separator rather than a normal word
            # boundary -- wrong case and/or wrong separator, e.g.
            # "explore: Foo" or "Explore - Foo". A bare "Explore" or a
            # plain "Explore Zone" (no separator-like punctuation after
            # the word) isn't an attempt -- General, not malformed.
            return ParsedListName(intent=None, category=None, malformed=True)

    if _SEPARATOR in name:
        # Shaped like `{word}: {rest}` but `word` isn't a recognized
        # Intent -- presumed an attempted/misspelled prefix rather than a
        # deliberately colon-containing General List name (accepted
        # tradeoff, see module docstring).
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
