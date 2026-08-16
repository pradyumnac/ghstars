import json
import subprocess
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import cast

from ghstars.core.models import List, RateLimitStatus, Star
from ghstars.github.schema import (
    FollowingNode,
    FollowingResponse,
    OwnedRepoNode,
    OwnedReposResponse,
    PageInfo,
    RateLimitResponse,
    RemoveStarResponse,
    RepositoryIdResponse,
    StarredEdge,
    StarredResponse,
)

PAGE_SIZE = 100
# A sync makes several paginated calls; require enough headroom that one
# doesn't get stuck mid-way through a large starred-repos list (story 13).
MIN_RATE_LIMIT_REMAINING = 50
_GH_TIMEOUT_SECONDS = 30.0

_STARRED_QUERY = f"""
query($cursor: String) {{
  viewer {{
    starredRepositories(
      first: {PAGE_SIZE}
      after: $cursor
      orderBy: {{field: STARRED_AT, direction: DESC}}
    ) {{
      pageInfo {{ hasNextPage endCursor }}
      edges {{
        starredAt
        node {{
          nameWithOwner
          url
          description
          primaryLanguage {{ name }}
          stargazerCount
        }}
      }}
    }}
  }}
}}
"""

_OWNED_FORKS_QUERY = f"""
query($cursor: String) {{
  viewer {{
    repositories(
      first: {PAGE_SIZE}
      after: $cursor
      affiliations: [OWNER]
      isFork: true
    ) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{ parent {{ nameWithOwner }} }}
    }}
  }}
}}
"""

_FOLLOWING_QUERY = f"""
query($cursor: String) {{
  viewer {{
    following(first: {PAGE_SIZE}, after: $cursor) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{ login }}
    }}
  }}
}}
"""

_RATE_LIMIT_QUERY = "query { rateLimit { remaining limit } }"

_REPOSITORY_ID_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    id
  }
}
"""

_REMOVE_STAR_MUTATION = """
mutation($starrableId: ID!) {
  removeStar(input: {starrableId: $starrableId}) {
    starrable {
      id
    }
  }
}
"""


class GitHubApiError(RuntimeError):
    """A `gh api graphql` call failed, timed out, or returned malformed data."""


def _graphql(
    query: str, cursor: str | None = None, **variables: str
) -> dict[str, object]:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if cursor is not None:
        cmd += ["-f", f"cursor={cursor}"]
    for name, value in variables.items():
        cmd += ["-f", f"{name}={value}"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_GH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitHubApiError(
            f"gh api graphql timed out after {_GH_TIMEOUT_SECONDS}s"
        ) from exc

    if result.returncode != 0:
        raise GitHubApiError(result.stderr.strip() or "gh api graphql failed")

    try:
        payload = cast(dict[str, object], json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        raise GitHubApiError("gh api graphql returned malformed JSON") from exc

    if payload.get("errors"):
        raise GitHubApiError(str(payload["errors"]))

    data = payload.get("data")
    if not isinstance(data, dict):
        raise GitHubApiError("gh api graphql returned no data")
    return cast(dict[str, object], data)


def _paginate_all[T](
    query: str, parse_page: Callable[[dict[str, object]], tuple[list[T], PageInfo]]
) -> Iterator[T]:
    cursor: str | None = None
    while True:
        data = _graphql(query, cursor=cursor)
        items, page_info = parse_page(data)
        yield from items

        if not page_info.has_next_page:
            return
        if page_info.end_cursor is None:
            raise GitHubApiError(
                "gh api graphql: hasNextPage=true but endCursor is null"
            )
        cursor = page_info.end_cursor


def _parse_starred_page(data: dict[str, object]) -> tuple[list[StarredEdge], PageInfo]:
    conn = StarredResponse.model_validate(data).viewer.starred_repositories
    return conn.edges, conn.page_info


def _parse_owned_forks_page(
    data: dict[str, object],
) -> tuple[list[OwnedRepoNode], PageInfo]:
    conn = OwnedReposResponse.model_validate(data).viewer.repositories
    return conn.nodes, conn.page_info


def _parse_following_page(
    data: dict[str, object],
) -> tuple[list[FollowingNode], PageInfo]:
    conn = FollowingResponse.model_validate(data).viewer.following
    return conn.nodes, conn.page_info


class RealGitHubClient:
    """ghstars.core.GitHubClient over `gh api graphql`.

    fetch_stars, check_rate_limit, and remove_star are implemented here —
    List reads land in ticket 03, List/membership mutations in ticket 04.
    Those methods exist to satisfy the GitHubClient Protocol and raise
    NotImplementedError until their own ticket lands.
    """

    def check_rate_limit(self) -> RateLimitStatus:
        data = _graphql(_RATE_LIMIT_QUERY)
        parsed = RateLimitResponse.model_validate(data)
        return RateLimitStatus(
            remaining=parsed.rate_limit.remaining,
            limit=parsed.rate_limit.limit,
            ok=parsed.rate_limit.remaining > MIN_RATE_LIMIT_REMAINING,
        )

    def fetch_stars(self) -> list[Star]:
        forked_parents = self._fetch_forked_parents()
        followed_logins = self._fetch_followed_logins()

        now = datetime.now(UTC)
        stars: list[Star] = []
        for edge in _paginate_all(_STARRED_QUERY, _parse_starred_page):
            node = edge.node
            owner_login = node.name_with_owner.split("/", 1)[0]
            stars.append(
                Star(
                    full_name=node.name_with_owner,
                    html_url=node.url,
                    description=node.description,
                    starred_at=edge.starred_at,
                    first_seen=now,
                    language=(
                        node.primary_language.name if node.primary_language else None
                    ),
                    stargazer_count=node.stargazer_count,
                    fork=node.name_with_owner in forked_parents,
                    follow=owner_login in followed_logins,
                    last_checked=now,
                )
            )
        return stars

    def _fetch_forked_parents(self) -> set[str]:
        return {
            node.parent.name_with_owner
            for node in _paginate_all(_OWNED_FORKS_QUERY, _parse_owned_forks_page)
            if node.parent is not None
        }

    def _fetch_followed_logins(self) -> set[str]:
        return {
            node.login
            for node in _paginate_all(_FOLLOWING_QUERY, _parse_following_page)
        }

    # --- Out of scope for ticket 02 ---

    def fetch_lists(self) -> list[List]:
        raise NotImplementedError("List fetching lands in ticket 03")

    def create_list(
        self, name: str, *, is_private: bool = False, description: str | None = None
    ) -> List:
        raise NotImplementedError("List mutations land in ticket 04")

    def update_list(
        self,
        list_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        is_private: bool | None = None,
    ) -> List:
        raise NotImplementedError("List mutations land in ticket 04")

    def delete_list(self, list_id: str) -> None:
        raise NotImplementedError("List mutations land in ticket 04")

    def update_list_membership_for_item(
        self, item_id: str, list_ids: list[str]
    ) -> None:
        raise NotImplementedError("List membership push lands in ticket 04")

    def remove_star(self, item_id: str) -> None:
        """Unstar `item_id` (a `full_name`, e.g. `owner/repo`) for real.

        GraphQL's `removeStar` mutation takes GitHub's opaque node ID
        (`starrableId`), not `owner/repo` — so this first resolves the
        node ID via `repository(owner, name) { id }`, then fires the
        mutation. Both calls go through `_graphql`; the resolve step costs
        one extra round trip per unstar, which is fine for a single,
        explicitly user-initiated action (not a batch/paginated path).
        """
        owner, _, name = item_id.partition("/")
        id_data = _graphql(_REPOSITORY_ID_QUERY, owner=owner, name=name)
        repo = RepositoryIdResponse.model_validate(id_data).repository
        if repo is None:
            raise GitHubApiError(
                f"repository {item_id!r} not found on GitHub "
                "(it may have been renamed or deleted)"
            )

        mutation_data = _graphql(_REMOVE_STAR_MUTATION, starrableId=repo.id)
        payload = RemoveStarResponse.model_validate(mutation_data).remove_star
        if payload.starrable is None:
            raise GitHubApiError(
                f"removeStar for {item_id!r} returned no starrable "
                "(GitHub may not have applied the mutation)"
            )
