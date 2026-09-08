"""Diagnose a GitHub account against this repo's taxonomy rules.

Emits a remediation plan; never prompts. Ticket 30 Scope 0 requires every
stable command to work without a terminal, so the interactive walkthrough
belongs to the skill layer that reads this report.
"""

from collections.abc import Iterable

from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import Intent, List
from ghstars.core.taxonomy import blessed_categories, classify_list

PROBLEM_MALFORMED = "malformed"
PROBLEM_UNBLESSED = "unblessed"


class ListProblem(BaseModel):
    list_name: str
    problem: str
    detail: str
    # Both repairs are valid; ghstars never picks one (ticket 03).
    repairs: list[str]


class DoctorReport(BaseModel):
    ok: bool
    list_count: int
    problems: list[ListProblem] = []
    missing_categories: list[str] = []
    create_blocked: bool = False
    blocked_reason: str | None = None


def diagnose(lists: list[List], *, categories: Iterable[str]) -> DoctorReport:
    """Check every List name against the shape rules and the vocabulary."""
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
                    repairs=[f"rename {lst.name!r} to a valid '{{Intent}}: {{Category}}'"],
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

    present = {lst.category for lst in classified if lst.category is not None}
    missing = sorted(blessed - present)

    return DoctorReport(
        ok=not problems and not missing,
        list_count=len(lists),
        problems=problems,
        missing_categories=missing,
        create_blocked=bool(problems),
        blocked_reason=(
            f"{len(problems)} List name(s) need attention first" if problems else None
        ),
    )


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
    "ListProblem",
    "bootstrap_lists",
    "diagnose",
    "planned_creates",
]
