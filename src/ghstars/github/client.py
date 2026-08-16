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
    RepositoryItemNode,
    StarredEdge,
    StarredResponse,
    UserListItemsNodeResponse,
    UserListNode,
    UserListsResponse,
)

PAGE_SIZE = 100
# A sync makes several paginated calls; require enough headroom that one
# does not get stuck mid-way through a large starred-repos list (story 13).
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

_LISTS_QUERY = f"""
query($cursor: String) {{
  viewer {{
    lists(first: {PAGE_SIZE}, after: $cursor) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{
        id
        name
        slug
        description
        isPrivate
      }}
    }}
  }}
}}
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


def _parse_lists_page(data: dict[str, object]) -> tuple[list[UserListNode], PageInfo]:
    conn = UserListsResponse.model_validate(data).viewer.lists
    return conn.nodes, conn.page_info


def _list_items_query(list_id: str) -> str:
    # list_id is opaque (e.g. "UL_kwDO..."). _graphql only threads a
    # $cursor variable, so bake list_id into the query text. json.dumps
    # escapes it safely as a GraphQL string literal.
    return f"""
query($cursor: String) {{
  node(id: {json.dumps(list_id)}) {{
    ... on UserList {{
      items(first: {PAGE_SIZE}, after: $cursor) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ ... on Repository {{ nameWithOwner }} }}
      }}
    }}
  }}
}}
"""


def _parse_list_items_page(
    data: dict[str, object],
) -> tuple[list[RepositoryItemNode | None], PageInfo]:
    parsed = UserListItemsNodeResponse.model_validate(data)
    if parsed.node is None:
        return [], PageInfo(has_next_page=False, end_cursor=None)
    conn = parsed.node.items
    return conn.nodes, conn.page_info


class RealGitHubClient:
    """ghstars.core.GitHubClient over `gh api graphql`.

    fetch_stars, fetch_lists, check_rate_limit, and remove_star are
    implemented. List/membership mutations (create_list, update_list,
    delete_list, update_list_membership_for_item) raise
    NotImplementedError until ticket 04.
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

    def fetch_lists(self) -> list[List]:
        """Fetch `viewer.lists` with each List's full item membership.

        Raw `name`/`description` only. `ghstars.core.taxonomy` classifies
        Intent/Category in `sync()`, not here.
        """
        lists: list[List] = []
        for node in _paginate_all(_LISTS_QUERY, _parse_lists_page):
            lists.append(
                List(
                    id=node.id,
                    name=node.name,
                    slug=node.slug,
                    description=node.description,
                    is_private=node.is_private,
                    items=self._fetch_list_items(node.id),
                )
            )
        return lists

    def _fetch_list_items(self, list_id: str) -> list[str]:
        query = _list_items_query(list_id)
        return [
            item.name_with_owner
            for item in _paginate_all(query, _parse_list_items_page)
            if item is not None and item.name_with_owner is not None
        ]

    # --- List/membership mutations: ticket 04 ---

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

        `removeStar` needs GitHub's node ID (`starrableId`), not
        `owner/repo`. Resolve the node ID via `repository(owner, name)
        { id }` first, then call the mutation. One extra round trip per
        unstar; acceptable for a single user-initiated action.
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
