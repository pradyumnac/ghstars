"""Diagnose a GitHub account against this repo's taxonomy rules.

Emits a remediation plan; never prompts. Ticket 30 Scope 0 requires every
stable command to work without a terminal, so the interactive walkthrough
belongs to the skill layer that reads this report.
"""

from collections.abc import Iterable

from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import Intent, List
from ghstars.core.taxonomy import (
    TRIAGE_CATEGORY,
    blessed_categories,
    check_writable_list_name,
    classify_list,
)

PROBLEM_MALFORMED = "malformed"
PROBLEM_UNBLESSED = "unblessed"


class ListProblem(BaseModel):
    list_name: str
    problem: str
    detail: str
    # Both repairs are valid; ghstars never picks one (ticket 03).
    repairs: list[str]


class StarProblem(BaseModel):
    """A Star in the triage inbox (`*: General`) and a classified List at
    once -- the same contradiction `verify_state` reports, computed here
    from live `List.items` rather than local `Star.list_ids`.
    """

    full_name: str
    in_triage_inbox: list[str]
    classified: list[str]
    # One `ghstars untag` call per inbox membership -- the repair that
    # only drops that one membership, keeping the rest.
    repairs: list[str]


class DoctorReport(BaseModel):
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
        inbox = [lst for lst in member_lists if lst.category == TRIAGE_CATEGORY]
        classified_lists = [
            lst
            for lst in member_lists
            if lst.category is not None and lst.category != TRIAGE_CATEGORY
        ]
        if inbox and classified_lists:
            found.append(
                StarProblem(
                    full_name=full_name,
                    in_triage_inbox=sorted(lst.name for lst in inbox),
                    classified=sorted(lst.name for lst in classified_lists),
                    repairs=[
                        f"ghstars untag {full_name} {lst.name!r}"
                        for lst in sorted(inbox, key=lambda lst: lst.name)
                    ],
                )
            )
    return sorted(found, key=lambda p: p.full_name)


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
                    # target name is the user's to choose.
                    repairs=[
                        f"ghstars remote rename-list {lst.name!r} '<new name>'"
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
        ok=not problems and not star_problems and not missing,
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
    if old_name == new_name:
        return classify_list(target)
    if any(lst.name == new_name for lst in lists if lst.id != target.id):
        raise ListNameTakenError(new_name)

    check_writable_list_name(new_name, categories)
    return classify_list(client.update_list(target.id, name=new_name))


def planned_creates(report: DoctorReport, *, intent: Intent) -> list[str]:
    """The List names `--fix` would create for `intent`."""
    return [f"{intent}: {category}" for category in report.missing_categories]


def bootstrap_lists(
    client: GitHubClient,
    report: DoctorReport,
    *,
    intent: Intent,
    is_private: bool = False,
) -> list[str]:
    """Create one List per missing blessed Category. Caller checks the gate."""
    created: list[str] = []
    for name in planned_creates(report, intent=intent):
        client.create_list(name, is_private=is_private)
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
