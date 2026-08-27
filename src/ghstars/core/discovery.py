"""The one Star discovery query shared by every surface.

Before this module existed, `ghstars.tui.app` held the only implementation
of Star filtering, search, and sort, and the CLI had none. This module is
that logic, moved into `ghstars.core` so the TUI and (later) the CLI call
the same code and can never disagree about what a query returns.

Row shape
---------
`query_stars()` returns `StarRow` values, not bare `Star` values. A row
pairs a `Star` with the *names* of the Lists it belongs to
(`list_names`), pre-resolved from the `list_ids`/`List.id` join. A wrapper
type was chosen over adding a field to `Star` itself: `Star` is a
persisted model (round-tripped through `state/stars.json`), and List-name
resolution is a query-time join that depends on which `List`s a caller
passed in, not a fact intrinsic to the Star. Bolting a derived field onto
the persisted model would invite it to drift out of sync with `list_ids`,
or worse, get serialized. A caller (the TUI, the CLI, or a future agent
skill) never joins `list_ids` against `List`s itself; it reads
`row.list_names` instead.

Compose order
-------------
`query_stars()` applies its steps in this fixed order, deterministically,
every call:

1. Archived exclusion (`include_archived`, default `False`).
2. Filters, AND-combined, in the order given.
3. Search (case-insensitive substring match on name and description).
4. Sort.
5. `offset`/`limit` (pagination over the sorted, filtered rows).

Filter grammar
--------------
Filters are plain strings, the same vocabulary the TUI already persists
to `state/tui-state.toml` (`filter`) and `config/tui.toml`
(`default_filter`). This module does not invent a new grammar — changing
that wire format is out of scope here.

    category:<name>       Star belongs to a List in this Category.
    intent:<name>          Star belongs to a List with this Intent.
    list:<list-id>          Star belongs to this exact List.
    language:<name>         Star's primary language matches exactly.
    license:<name>          Star's license matches exactly.
    owner:<name>             Star's owner (the part of full_name before "/").
    forks                    Star is a fork.
    followed                 Star's owner is followed.
    unclassified              Star belongs to no List.
    recent:1d|1w|1m|3m|1y     Star was starred within this window.
    recent:older_1y           Star was starred more than a year ago.

`query_stars()` accepts zero or more Filter keys and AND-combines them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from ghstars.core.models import List, Star

# -- recency ------------------------------------------------------------------

# ADR 0008 rejected making these cutoffs configurable. Do not add a config
# knob for them.
RECENCY_CUTOFFS: dict[str, timedelta] = {
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
    "1y": timedelta(days=365),
}
OLDER_THAN_CUTOFF = timedelta(days=365)

# -- sort -----------------------------------------------------------------

SortMode = Literal[
    "name_asc",
    "name_desc",
    "starred_asc",
    "starred_desc",
    "stargazer_asc",
    "stargazer_desc",
    "language_asc",
    "language_desc",
    "list_count_asc",
    "list_count_desc",
    "list_name_asc",
    "list_name_desc",
]

DEFAULT_SORT: SortMode = "starred_desc"

# Whether the exclusion of Archived Stars applies unless a caller opts in.
DEFAULT_INCLUDE_ARCHIVED = False


@dataclass(frozen=True)
class StarRow:
    """One query result: a Star plus its resolved List names.

    `list_names` is sorted alphabetically. A Star in no List gets an
    empty list, never `None`.
    """

    star: Star
    list_names: list[str]


@dataclass(frozen=True)
class Facets:
    """Available facet values for a given set of Stars and Lists.

    Mirrors what the TUI's Filter menu enumerates today: every value is
    dependent on what data is present, not a fixed vocabulary. Categories,
    Intents, and Lists come from the Lists given; Languages, Licenses, and
    Owners come from the Stars given.
    """

    categories: list[str]
    intents: list[str]
    lists: list[List]
    languages: list[str]
    licenses: list[str]
    owners: list[str]


def _lists_by_id(lists: Sequence[List]) -> dict[str, List]:
    return {lst.id: lst for lst in lists}


def _list_names_for(star: Star, by_id: dict[str, List]) -> list[str]:
    return sorted(by_id[lid].name for lid in star.list_ids if lid in by_id)


def _apply_one_filter(
    stars: list[Star], lists: Sequence[List], filter_key: str
) -> list[Star]:
    """Apply a single Filter key. Unknown keys and the empty string pass
    every Star through unchanged, matching the TUI's historical "no
    filter" behaviour for an unrecognised key.
    """
    if not filter_key:
        return stars
    if filter_key == "unclassified":
        return [star for star in stars if not star.list_ids]
    if filter_key == "forks":
        return [star for star in stars if star.fork]
    if filter_key == "followed":
        return [star for star in stars if star.follow]
    if filter_key.startswith("category:"):
        category = filter_key.removeprefix("category:")
        ids = {lst.id for lst in lists if lst.category == category}
        return [star for star in stars if set(star.list_ids) & ids]
    if filter_key.startswith("intent:"):
        intent = filter_key.removeprefix("intent:")
        ids = {lst.id for lst in lists if lst.intent == intent}
        return [star for star in stars if set(star.list_ids) & ids]
    if filter_key.startswith("list:"):
        list_id = filter_key.removeprefix("list:")
        return [star for star in stars if list_id in star.list_ids]
    if filter_key.startswith("language:"):
        language = filter_key.removeprefix("language:")
        return [star for star in stars if star.language == language]
    if filter_key.startswith("license:"):
        license_name = filter_key.removeprefix("license:")
        return [star for star in stars if star.license == license_name]
    if filter_key.startswith("owner:"):
        owner = filter_key.removeprefix("owner:")
        return [star for star in stars if star.full_name.split("/", 1)[0] == owner]
    if filter_key.startswith("recent:"):
        recency = filter_key.removeprefix("recent:")
        now = datetime.now(UTC)
        if recency == "older_1y":
            cutoff = now - OLDER_THAN_CUTOFF
            return [star for star in stars if star.starred_at < cutoff]
        window = RECENCY_CUTOFFS.get(recency)
        if window is None:
            return stars
        cutoff = now - window
        return [star for star in stars if star.starred_at >= cutoff]
    return stars


def _apply_search(stars: list[Star], search: str) -> list[Star]:
    query = search.strip().lower()
    if not query:
        return stars
    return [
        star
        for star in stars
        if query in star.full_name.lower()
        or (star.description is not None and query in star.description.lower())
    ]


def _sort_stars(stars: list[Star], lists: Sequence[List], sort: SortMode) -> list[Star]:
    field, _, direction = sort.rpartition("_")
    reverse = direction == "desc"
    if field == "name":
        return sorted(stars, key=lambda s: s.full_name, reverse=reverse)
    if field == "starred":
        return sorted(stars, key=lambda s: s.starred_at, reverse=reverse)
    if field == "stargazer":
        return sorted(stars, key=lambda s: s.stargazer_count, reverse=reverse)
    if field == "language":
        return sorted(
            stars,
            key=lambda s: (s.language is None, s.language or ""),
            reverse=reverse,
        )
    if field == "list_count":
        return sorted(stars, key=lambda s: len(s.list_ids), reverse=reverse)
    if field == "list_name":
        by_id = _lists_by_id(lists)

        def _first_list_name(star: Star) -> tuple[bool, str]:
            names = _list_names_for(star, by_id)
            return (not names, names[0] if names else "")

        return sorted(stars, key=_first_list_name, reverse=reverse)
    raise ValueError(f"unknown sort mode: {sort!r}")


def query_stars(
    stars: Sequence[Star],
    lists: Sequence[List],
    *,
    filters: Sequence[str] = (),
    search: str = "",
    sort: SortMode = DEFAULT_SORT,
    include_archived: bool = DEFAULT_INCLUDE_ARCHIVED,
    limit: int | None = None,
    offset: int = 0,
) -> list[StarRow]:
    """Filter, search, sort, and paginate Stars. See the module docstring
    for the compose order and the Filter grammar.

    `filters` are AND-combined: a Star must pass every Filter given to
    appear in the result. A repeated call with the same arguments over
    the same input always returns the same rows in the same order.
    """
    result = list(stars)
    if not include_archived:
        result = [star for star in result if not star.archived]
    for filter_key in filters:
        result = _apply_one_filter(result, lists, filter_key)
    result = _apply_search(result, search)
    result = _sort_stars(result, lists, sort)

    if offset:
        result = result[offset:]
    if limit is not None:
        result = result[:limit]

    by_id = _lists_by_id(lists)
    return [
        StarRow(star=star, list_names=_list_names_for(star, by_id)) for star in result
    ]


def available_facets(stars: Sequence[Star], lists: Sequence[List]) -> Facets:
    """Enumerate the facet values available in a given Stars/Lists set.

    Mirrors the TUI's Filter menu enumeration. Callers decide whether to
    exclude Archived Stars first (pass an already-filtered `stars`
    sequence) — this function does not filter Archived Stars itself.
    """
    return Facets(
        categories=sorted({lst.category for lst in lists if lst.category}),
        intents=sorted({lst.intent for lst in lists if lst.intent}),
        lists=sorted(lists, key=lambda lst: lst.name),
        languages=sorted({star.language for star in stars if star.language}),
        licenses=sorted({star.license for star in stars if star.license}),
        owners=sorted({star.full_name.split("/", 1)[0] for star in stars}),
    )
