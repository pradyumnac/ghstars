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
from collections.abc import Iterable, Sequence
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


class UnwritableListNameError(Exception):
    """ghstars would have written a List name it cannot parse (ADR 0005).

    Guards every write path that takes a raw name from the user:
    `tag_star`'s create, and `rename_list`. A name that already exists on
    GitHub is never judged this way -- ADR 0001 keeps GitHub the source
    of truth, so `verify`/`doctor` report those instead.
    """

    def __init__(self, list_name: str, reason: str) -> None:
        self.list_name = list_name
        self.reason = reason
        super().__init__(f"cannot write List name {list_name!r}: {reason}")


def check_writable_list_name(list_name: str, categories: Iterable[str]) -> None:
    """Raise `UnwritableListNameError` unless ghstars may write this name.

    `categories` is required. There is always a vocabulary -- a missing
    `ghstars.toml` still yields `DEFAULT_CATEGORIES` -- so an optional
    parameter could only ever mean "the caller forgot", which is how the
    TUI bypassed this guard entirely.
    """
    parsed = parse_list_name(list_name)
    if parsed.malformed:
        raise UnwritableListNameError(
            list_name,
            "the name attempts the '{Intent}: {Category}' pattern and does not "
            "match it",
        )
    if parsed.category is None:
        return
    if parsed.category not in blessed_categories(categories):
        raise UnwritableListNameError(
            list_name,
            f"Category {parsed.category!r} is not in the [taxonomy] table of "
            "ghstars.toml -- add it there, or use a blessed Category",
        )


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


@dataclass(frozen=True)
class StarConflicts:
    """Which Star-level taxonomy rules a Star's List memberships break.

    The one place these rules live (ADR 0005). `verify_state` feeds it
    local `Star.list_ids`; `doctor` feeds it live `List.items`. Neither
    re-derives a rule, so the two reporters cannot drift apart.
    """

    triage_inbox: list[List]
    classified: list[List]
    lifecycle_intents: list[Intent]

    @property
    def in_inbox_and_classified(self) -> bool:
        """`General` says the subject is undecided; a Category says it is not."""
        return bool(self.triage_inbox and self.classified)

    @property
    def has_lifecycle_conflict(self) -> bool:
        """At most one of Explore/Current/Retired, across all of a Star's Lists."""
        return len(self.lifecycle_intents) > 1

    @property
    def ok(self) -> bool:
        return not self.in_inbox_and_classified and not self.has_lifecycle_conflict


def star_conflicts(member_lists: Sequence[List]) -> StarConflicts:
    """Evaluate every Star-level rule against the Lists a Star belongs to."""
    return StarConflicts(
        triage_inbox=[lst for lst in member_lists if lst.category == TRIAGE_CATEGORY],
        classified=[
            lst
            for lst in member_lists
            if lst.category is not None and lst.category != TRIAGE_CATEGORY
        ],
        lifecycle_intents=sorted(
            {
                lst.intent
                for lst in member_lists
                if lst.intent is not None and lst.intent in LIFECYCLE_INTENTS
            }
        ),
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
