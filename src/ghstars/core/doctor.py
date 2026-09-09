"""Diagnose a GitHub account against this repo's taxonomy rules.

Emits a remediation plan; never prompts. Ticket 30 Scope 0 requires every
stable command to work without a terminal, so the interactive walkthrough
belongs to the skill layer that reads this report.
"""

import shlex
from collections.abc import Iterable

from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import Intent, List
from ghstars.core.taxonomy import (
    blessed_categories,
    check_writable_list_name,
    classify_list,
    parse_list_name,
    star_conflicts,
)
from ghstars.github import GitHubApiError

PROBLEM_MALFORMED = "malformed"
PROBLEM_UNBLESSED = "unblessed"
PROBLEM_INBOX_AND_CLASSIFIED = "inbox_and_classified"
PROBLEM_TWO_LIFECYCLES = "two_lifecycle_intents"


class ListProblem(BaseModel):
    list_name: str
    problem: str
    detail: str
    # Both repairs are valid; ghstars never picks one (ticket 03).
    repairs: list[str]


class StarProblem(BaseModel):
    """A Star breaking a Star-level taxonomy rule, from live `List.items`.

    Same rules `verify_state` applies to local state -- both call
    `taxonomy.star_conflicts`, so the two reporters cannot diverge.
    """

    full_name: str
    problem: str
    detail: str
    in_triage_inbox: list[str] = []
    classified: list[str] = []
    lifecycle_intents: list[str] = []
    # True when `repairs` reads local state, so `ghstars sync` must run
    # first. `untag` does; nothing else here reads it.
    requires_sync: bool = False
    repairs: list[str] = []


class DoctorReport(BaseModel):
    # `ok` covers defects only, never `missing_categories`.
    ok: bool
    list_count: int
    problems: list[ListProblem] = []
    star_problems: list[StarProblem] = []
    missing_categories: list[str] = []
    create_blocked: bool = False
    blocked_reason: str | None = None


def _star_problems(classified: list[List]) -> list[StarProblem]:
    membership: dict[str, list[List]] = {}
    for lst in classified:
        for full_name in lst.items:
            membership.setdefault(full_name, []).append(lst)

    found: list[StarProblem] = []
    for full_name, member_lists in membership.items():
        conflicts = star_conflicts(member_lists)
        if conflicts.in_inbox_and_classified:
            found.append(
                StarProblem(
                    full_name=full_name,
                    problem=PROBLEM_INBOX_AND_CLASSIFIED,
                    detail="in the triage inbox and a classified List at once",
                    in_triage_inbox=sorted(lst.name for lst in conflicts.triage_inbox),
                    classified=sorted(lst.name for lst in conflicts.classified),
                    requires_sync=True,
                    repairs=[
                        f"ghstars untag {shlex.quote(full_name)} "
                        f"{shlex.quote(lst.name)}"
                        for lst in sorted(
                            conflicts.triage_inbox, key=lambda lst: lst.name
                        )
                    ],
                )
            )
        if conflicts.has_lifecycle_conflict:
            # Two valid repairs (which Intent is right?), so prose only.
            found.append(
                StarProblem(
                    full_name=full_name,
                    problem=PROBLEM_TWO_LIFECYCLES,
                    detail=(
                        "holds lifecycle Intents "
                        f"{list(conflicts.lifecycle_intents)}; at most one of "
                        "Explore/Current/Retired applies to a Star"
                    ),
                    lifecycle_intents=list(conflicts.lifecycle_intents),
                    classified=sorted(
                        lst.name
                        for lst in member_lists
                        if lst.intent in conflicts.lifecycle_intents
                    ),
                    repairs=[
                        (
                            "keep one lifecycle Intent: re-tag the Star, or "
                            "untag it from the Lists that no longer apply"
                        )
                    ],
                )
            )
    return sorted(found, key=lambda p: (p.full_name, p.problem))


def diagnose(lists: list[List], *, categories: Iterable[str]) -> DoctorReport:
    """Check every List name against the shape rules and the vocabulary,
    and every Star against the triage-inbox invariant.
    """
    classified = [classify_list(lst) for lst in lists]
    blessed = blessed_categories(categories)

    problems: list[ListProblem] = []
    for lst in classified:
        if lst.malformed:
            problems.append(
                ListProblem(
                    list_name=lst.name,
                    problem=PROBLEM_MALFORMED,
                    detail="name attempts '{Intent}: {Category}' and does not match",
                    # One repair type, so the command is concrete; only the
                    # target name is the user's to choose. `shlex.quote`,
                    # not `repr`: a name holding an apostrophe makes `repr`
                    # emit double quotes, which a shell would expand.
                    repairs=[
                        (
                            "ghstars remote rename-list "
                            f"{shlex.quote(lst.name)} '<new name>' --yes"
                        )
                    ],
                )
            )
        elif lst.category is not None and lst.category not in blessed:
            problems.append(
                ListProblem(
                    list_name=lst.name,
                    problem=PROBLEM_UNBLESSED,
                    detail=f"Category {lst.category!r} is not in [taxonomy]",
                    repairs=[
                        f"add {lst.category!r} to [taxonomy] in ghstars.toml",
                        f"rename {lst.name!r} to use a blessed Category",
                    ],
                )
            )

    star_problems = _star_problems(classified)

    present = {lst.category for lst in classified if lst.category is not None}
    missing = sorted(blessed - present)

    return DoctorReport(
        # `missing` is deliberately excluded: a blessed Category with no
        # List is an opportunity, not a defect. Folding it in would leave
        # `ok` false forever, since the default vocabulary ships 12.
        ok=not problems and not star_problems,
        list_count=len(lists),
        problems=problems,
        star_problems=star_problems,
        missing_categories=missing,
        create_blocked=bool(problems),
        blocked_reason=(
            f"{len(problems)} List name(s) need attention first" if problems else None
        ),
    )


class ListNotFoundError(Exception):
    """`remote rename-list` targeted a List GitHub does not have."""

    def __init__(self, list_name: str) -> None:
        self.list_name = list_name
        super().__init__(f"no List named {list_name!r} on GitHub")


class ListNameTakenError(Exception):
    """`remote rename-list`'s target name belongs to a different List."""

    def __init__(self, list_name: str) -> None:
        self.list_name = list_name
        super().__init__(f"{list_name!r} is already another List's name")


def rename_list(
    client: GitHubClient,
    old_name: str,
    new_name: str,
    *,
    categories: Iterable[str] | None = None,
) -> List:
    """Rename exactly one List, against live GitHub state only.

    No local store and no lock: a rename changes List identity, never
    Star membership, so there is nothing to reconcile (ADR 0001). That
    is why this needs no prior `sync`, unlike `category rename` -- and
    unlike it, this can change a List's Intent, the gap hit renaming
    `Learning` to `Learn: General`.

    Refuses a malformed or unblessed `new_name`, with no override: this
    exists to move a List out of a bad name, never into one.

    `lists.json` is stale afterwards. Run `ghstars sync`.
    """
    lists = client.fetch_lists()
    target = next((lst for lst in lists if lst.name == old_name), None)
    if target is None:
        raise ListNotFoundError(old_name)

    # Validate before the no-op check, so renaming a malformed name to
    # itself reports the problem instead of a bogus success.
    check_writable_list_name(new_name, categories)

    # Compare parsed identity, not just the raw name: `Explore: AI_Agents`
    # and `Explore: AI Agents` are one Category, and a duplicate of that
    # shape is one nothing downstream can flag.
    wanted = parse_list_name(new_name)
    for lst in lists:
        if lst.id == target.id:
            continue
        if lst.name == new_name:
            raise ListNameTakenError(new_name)
        other = parse_list_name(lst.name)
        if not other.malformed and (other.intent, other.category) == (
            wanted.intent,
            wanted.category,
        ):
            raise ListNameTakenError(lst.name)

    if old_name == new_name:
        return classify_list(target)
    return classify_list(client.update_list(target.id, name=new_name))


def planned_creates(
    report: DoctorReport,
    *,
    intent: Intent,
    only: Iterable[str] | None = None,
) -> list[str]:
    """The List names `remote bootstrap` would create for `intent`.

    Always the explicit `{Intent}: {Category}` form, including for
    `Reference`. A bare name parses to `Reference` too, but ghstars writes
    the Intent it means rather than relying on the default (ADR 0005).

    `only` selects a subset of the missing Categories, so Categories
    needing different Intents can be created in separate runs.
    """
    wanted = blessed_categories(only) if only is not None else None
    return [
        f"{intent}: {category}"
        for category in report.missing_categories
        if wanted is None or category in wanted
    ]


class PartialBootstrapError(Exception):
    """A create failed part-way. Names already created are reported, not lost."""

    def __init__(self, created: list[str], cause: Exception) -> None:
        self.created = created
        self.cause = cause
        super().__init__(f"created {len(created)} List(s), then failed: {cause}")


def bootstrap_lists(
    client: GitHubClient,
    report: DoctorReport,
    *,
    intent: Intent,
    is_private: bool = False,
    only: Iterable[str] | None = None,
) -> list[str]:
    """Create one List per missing blessed Category. Caller checks the gate.

    A mid-run failure raises `PartialBootstrapError` carrying what was
    already created, so the caller reports it rather than losing it.
    Re-running is safe: what exists is no longer missing.
    """
    created: list[str] = []
    for name in planned_creates(report, intent=intent, only=only):
        try:
            client.create_list(name, is_private=is_private)
        except GitHubApiError as exc:
            # Only a remote failure is partial-and-retryable. Anything else
            # is a defect here and must not be reported as a network error.
            raise PartialBootstrapError(created, exc) from exc
        created.append(name)
    return created


__all__ = [
    "PROBLEM_MALFORMED",
    "PROBLEM_UNBLESSED",
    "DoctorReport",
    "ListNameTakenError",
    "ListNotFoundError",
    "ListProblem",
    "StarProblem",
    "bootstrap_lists",
    "diagnose",
    "planned_creates",
    "rename_list",
]
