from datetime import UTC, datetime

from filelock import Timeout
from pydantic import BaseModel

from ghstars.core.github_client import GitHubClient
from ghstars.core.state_store import StateStore
from ghstars.core.sync import archive_star, remove_star_from_lists
from ghstars.github.client import GitHubApiError


class UnstarResult(BaseModel):
    """The result of `unstar_star()`.

    `found_locally` distinguishes "archived a known Star" from "the
    repo had no local record to archive" -- both are a successful
    unstar (the GitHub-side mutation already happened either way), but
    the caller's own message differs (`ghstars unstar`'s CLI output,
    the TUI's confirm-dialog result).
    """

    full_name: str
    found_locally: bool


def unstar_star(
    client: GitHubClient, store: StateStore, full_name: str
) -> UnstarResult:
    """Unstar `full_name` on GitHub for real, then archive it locally.

    Extracted from `cli.commands.unstar.unstar_cmd` (ticket 29's
    prefactor) so the CLI and the TUI's unstar action share one
    orchestration -- the CLI provably unchanged, the TUI never a second
    copy of the same lock/archive/save sequence.

    A real, visible GitHub mutation (spec story 8): `client.remove_star`
    is called before anything local changes, and is never retried or
    undone by this function -- a caller that wants a confirm step (the
    TUI's confirm dialog) must gate the call to this function itself,
    not anything inside it.

    Raises whatever `client.remove_star()` raises (`GitHubApiError`) or
    a `filelock.Timeout` from `store.lock()` -- both left for the
    caller to turn into its own user-facing message, same division of
    responsibility as `tag_star()`.
    """
    client.remove_star(full_name)

    # Hold the lock across the local read-modify-write after remote success.
    now = datetime.now(UTC)
    with store.lock():
        stars = store.load_stars()
        found_locally = any(star.full_name == full_name for star in stars)
        updated = [
            archive_star(star, now=now)
            if star.full_name == full_name and not star.archived
            else star
            for star in stars
        ]
        store.save_stars(updated)
        store.save_lists(remove_star_from_lists(store.load_lists(), full_name))

    return UnstarResult(full_name=full_name, found_locally=found_locally)


class BulkUnstarOutcome(BaseModel):
    """One repository's outcome from `bulk_unstar_stars()`.

    Exactly one of `result` and `error` is set, mirroring
    `tagging.BulkTagOutcome` (ticket 31, Scope C).
    """

    full_name: str
    result: UnstarResult | None = None
    error: str | None = None
    error_code: str | None = None


def bulk_unstar_stars(
    client: GitHubClient, store: StateStore, full_names: list[str]
) -> list[BulkUnstarOutcome]:
    """Unstar every repo in `full_names`, one `unstar_star()` call per
    repo, isolating each repo's failure from the others.

    Built for the CLI's bulk unstar (ticket 30) -- the TUI keeps
    refusing bulk unstar on blast-radius grounds (ticket 31, Scope B)
    and never calls this. Builds on `unstar_star()` rather than
    duplicating its lock/remove/archive sequence; unlike
    `bulk_tag_stars()` there is no shared snapshot to thread between
    calls -- each unstar is an independent GitHub `removeStar` mutation
    with no equivalent to `tag_star()`'s `lists` reuse.
    """
    outcomes: list[BulkUnstarOutcome] = []
    for full_name in full_names:
        try:
            result = unstar_star(client, store, full_name)
        except Timeout as exc:
            outcomes.append(
                BulkUnstarOutcome(
                    full_name=full_name,
                    error=str(exc),
                    error_code="state_lock_held",
                )
            )
            continue
        except GitHubApiError as exc:
            outcomes.append(
                BulkUnstarOutcome(
                    full_name=full_name,
                    error=str(exc),
                    error_code="network_failure",
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 -- isolate one repo's failure
            outcomes.append(
                BulkUnstarOutcome(
                    full_name=full_name,
                    error=str(exc),
                    error_code="unexpected_error",
                )
            )
            continue
        outcomes.append(BulkUnstarOutcome(full_name=full_name, result=result))
    return outcomes
