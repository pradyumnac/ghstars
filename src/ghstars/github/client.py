import json
import subprocess
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import cast

from ghstars.core.models import List, RateLimitStatus, Star
from ghstars.github.schema import (
    CreateUserListResponse,
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
    UpdateListsForItemResponse,
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

_CREATE_LIST_MUTATION = """
mutation($name: String!, $description: String, $isPrivate: Boolean) {
  createUserList(input: {name: $name, description: $description, isPrivate: $isPrivate}) {
    list {
      id
      name
      slug
      description
      isPrivate
    }
  }
}
"""

_UPDATE_LIST_MEMBERSHIP_MUTATION = """
mutation($itemId: ID!, $listIds: [ID!]!) {
  updateUserListsForItem(input: {itemId: $itemId, listIds: $listIds}) {
    item {
      __typename
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
    query: str,
    cursor: str | None = None,
    **variables: str | bool | list[str] | None,
) -> dict[str, object]:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if cursor is not None:
        cmd += ["-f", f"cursor={cursor}"]
    for name, value in variables.items():
        if value is None:
            continue
        if isinstance(value, bool):
            cmd += ["-F", f"{name}={'true' if value else 'false'}"]
        elif isinstance(value, list):
            if not value:
                cmd += ["-F", f"{name}[]"]
            else:
                for item in value:
                    cmd += ["-F", f"{name}[]={item}"]
        else:
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

    Implemented: fetch_stars, fetch_lists, check_rate_limit, remove_star,
    create_list, update_list_membership_for_item. update_list and
    delete_list raise NotImplementedError until ticket 07.
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

    def create_list(
        self, name: str, *, is_private: bool = False, description: str | None = None
    ) -> List:
        """Create a List for real via `createUserList`.

        Returns the raw List as GitHub created it (no Intent/Category —
        that's `ghstars.core.taxonomy`'s job at the caller).
        """
        data = _graphql(
            _CREATE_LIST_MUTATION,
            name=name,
            description=description,
            isPrivate=is_private,
        )
        payload = CreateUserListResponse.model_validate(data).create_user_list
        if payload.list is None:
            raise GitHubApiError(f"createUserList for {name!r} returned no list")
        node = payload.list
        return List(
            id=node.id,
            name=node.name,
            slug=node.slug,
            description=node.description,
            is_private=node.is_private,
        )

    def update_list(
        self,
        list_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        is_private: bool | None = None,
    ) -> List:
        raise NotImplementedError("List rename/description mutations land in ticket 07")

    def delete_list(self, list_id: str) -> None:
        raise NotImplementedError("List deletion lands in ticket 07")

    def update_list_membership_for_item(
        self, item_id: str, list_ids: list[str]
    ) -> None:
        """Replace `item_id`'s (a `full_name`) entire List membership.

        `updateUserListsForItem` replaces, it does not merge (the spec's
        load-bearing GraphQL detail) — `list_ids` must already be the
        full desired set, never a delta. Needs GitHub's node ID, not
        `owner/repo`; resolved the same way `remove_star` does.
        """
        node_id = self._resolve_repository_node_id(item_id)
        data = _graphql(
            _UPDATE_LIST_MEMBERSHIP_MUTATION, itemId=node_id, listIds=list_ids
        )
        payload = UpdateListsForItemResponse.model_validate(
            data
        ).update_user_lists_for_item
        if payload.item is None:
            raise GitHubApiError(
                f"updateUserListsForItem for {item_id!r} returned no item "
                "(GitHub may not have applied the mutation)"
            )

    def remove_star(self, item_id: str) -> None:
        """Unstar `item_id` (a `full_name`, e.g. `owner/repo`) for real."""
        node_id = self._resolve_repository_node_id(item_id)
        mutation_data = _graphql(_REMOVE_STAR_MUTATION, starrableId=node_id)
        payload = RemoveStarResponse.model_validate(mutation_data).remove_star
        if payload.starrable is None:
            raise GitHubApiError(
                f"removeStar for {item_id!r} returned no starrable "
                "(GitHub may not have applied the mutation)"
            )

    def _resolve_repository_node_id(self, item_id: str) -> str:
        """`item_id` is `owner/repo`; several mutations need GitHub's
        opaque node ID instead. One extra round trip per call. Used by
        `remove_star` (a single user-initiated action) and by
        `update_list_membership_for_item` from `sync()`'s per-star merge
        loop (`ghstars.core.sync._merge_pending_list_membership`) — N
        pending tags cost 2N sequential round trips per sync, not
        batched (see docs/explanation/known-limitations.md).
        """
        owner, _, name = item_id.partition("/")
        id_data = _graphql(_REPOSITORY_ID_QUERY, owner=owner, name=name)
        repo = RepositoryIdResponse.model_validate(id_data).repository
        if repo is None:
            raise GitHubApiError(
                f"repository {item_id!r} not found on GitHub "
                "(it may have been renamed or deleted)"
            )
        return repo.id
