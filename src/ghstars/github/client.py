import json
import logging
import subprocess
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import cast

from ghstars.core.models import List, RateLimitStatus, Star
from ghstars.github.schema import (
    CreateUserListResponse,
    DeleteUserListResponse,
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
    UpdateUserListResponse,
    UserListItemsNodeResponse,
    UserListNode,
    UserListsResponse,
)

# Fetcher logging is silent by default and enabled by the sync command.
logger = logging.getLogger("ghstars.github")

PAGE_SIZE = 100
# Reserve rate-limit headroom for paginated sync calls.
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
          licenseInfo {{ spdxId name }}
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

_UPDATE_LIST_MUTATION = """
mutation($listId: ID!, $name: String, $description: String, $isPrivate: Boolean) {
  updateUserList(input: {listId: $listId, name: $name, description: $description, isPrivate: $isPrivate}) {
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

_DELETE_LIST_MUTATION = """
mutation($listId: ID!) {
  deleteUserList(input: {listId: $listId}) {
    clientMutationId
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

    logger.debug("gh api graphql request: cursor=%r variables=%s", cursor, variables)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_GH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        logger.debug("gh api graphql: timed out after %ss", _GH_TIMEOUT_SECONDS)
        raise GitHubApiError(
            f"gh api graphql timed out after {_GH_TIMEOUT_SECONDS}s"
        ) from exc

    if result.returncode != 0:
        logger.debug(
            "gh api graphql: exit=%d stderr=%r", result.returncode, result.stderr
        )
        raise GitHubApiError(result.stderr.strip() or "gh api graphql failed")

    try:
        payload = cast(dict[str, object], json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        logger.debug("gh api graphql: malformed JSON stdout=%r", result.stdout)
        raise GitHubApiError("gh api graphql returned malformed JSON") from exc

    if payload.get("errors"):
        logger.debug("gh api graphql: errors=%s", payload["errors"])
        raise GitHubApiError(str(payload["errors"]))

    data = payload.get("data")
    if not isinstance(data, dict):
        logger.debug("gh api graphql: no data, payload=%s", payload)
        raise GitHubApiError("gh api graphql returned no data")
    logger.debug("gh api graphql response: keys=%s", list(data.keys()))
    return cast(dict[str, object], data)


def _paginate_all[T](
    query: str, parse_page: Callable[[dict[str, object]], tuple[list[T], PageInfo]]
) -> Iterator[T]:
    cursor: str | None = None
    page = 0
    while True:
        page += 1
        data = _graphql(query, cursor=cursor)
        items, page_info = parse_page(data)
        logger.debug(
            "paginate: page=%d items=%d has_next_page=%s",
            page,
            len(items),
            page_info.has_next_page,
        )
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
    # Embed the opaque list ID safely because only the cursor is a variable.
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


def _batched_repository_id_query(full_names: list[str]) -> str:
    # Build one aliased query that resolves all repository IDs in one request.
    fields = "\n".join(
        f"  r{index}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ id }}"
        for index, full_name in enumerate(full_names)
        for owner, _, name in [full_name.partition("/")]
    )
    return f"query {{\n{fields}\n}}"


class RealGitHubClient:
    """ghstars.core.GitHubClient over `gh api graphql`.

    Implemented: fetch_stars, fetch_lists, check_rate_limit, remove_star,
    create_list, update_list, delete_list, update_list_membership_for_item.
    """

    def check_rate_limit(self) -> RateLimitStatus:
        data = _graphql(_RATE_LIMIT_QUERY)
        parsed = RateLimitResponse.model_validate(data)
        status = RateLimitStatus(
            remaining=parsed.rate_limit.remaining,
            limit=parsed.rate_limit.limit,
            ok=parsed.rate_limit.remaining > MIN_RATE_LIMIT_REMAINING,
        )
        logger.debug(
            "check_rate_limit: remaining=%d limit=%d ok=%s",
            status.remaining,
            status.limit,
            status.ok,
        )
        return status

    def fetch_stars(self) -> list[Star]:
        logger.debug("fetch_stars: starting")
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
                    license=(
                        node.license_info.spdx_id or node.license_info.name
                        if node.license_info
                        else None
                    ),
                    stargazer_count=node.stargazer_count,
                    fork=node.name_with_owner in forked_parents,
                    follow=owner_login in followed_logins,
                    last_checked=now,
                )
            )
        logger.debug("fetch_stars: fetched %d star(s)", len(stars))
        return stars

    def _fetch_forked_parents(self) -> set[str]:
        parents = {
            node.parent.name_with_owner
            for node in _paginate_all(_OWNED_FORKS_QUERY, _parse_owned_forks_page)
            if node.parent is not None
        }
        logger.debug("fetch_stars: %d forked parent(s)", len(parents))
        return parents

    def _fetch_followed_logins(self) -> set[str]:
        logins = {
            node.login
            for node in _paginate_all(_FOLLOWING_QUERY, _parse_following_page)
        }
        logger.debug("fetch_stars: following %d login(s)", len(logins))
        return logins

    def fetch_lists(self) -> list[List]:
        """Fetch `viewer.lists` with each List's full item membership.

        Raw `name`/`description` only. `ghstars.core.taxonomy` classifies
        Intent/Category in `sync()`, not here.
        """
        logger.debug("fetch_lists: starting")
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
        logger.debug("fetch_lists: fetched %d list(s)", len(lists))
        return lists

    def _fetch_list_items(self, list_id: str) -> list[str]:
        query = _list_items_query(list_id)
        items = [
            item.name_with_owner
            for item in _paginate_all(query, _parse_list_items_page)
            if item is not None and item.name_with_owner is not None
        ]
        logger.debug("fetch_lists: list %s has %d item(s)", list_id, len(items))
        return items

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
        """Rename/redescribe/re-privacy an existing List via `updateUserList`.

        Returns the raw List as GitHub updated it (no Intent/Category —
        that's `ghstars.core.taxonomy`'s job at the caller, same
        convention as `create_list`). An omitted (`None`) field is left
        unchanged on GitHub's side — `updateUserList`'s input fields are
        all optional aside from `listId` (confirmed via live
        introspection, ticket 07).
        """
        data = _graphql(
            _UPDATE_LIST_MUTATION,
            listId=list_id,
            name=name,
            description=description,
            isPrivate=is_private,
        )
        payload = UpdateUserListResponse.model_validate(data).update_user_list
        if payload.list is None:
            raise GitHubApiError(f"updateUserList for {list_id!r} returned no list")
        node = payload.list
        return List(
            id=node.id,
            name=node.name,
            slug=node.slug,
            description=node.description,
            is_private=node.is_private,
        )

    def delete_list(self, list_id: str) -> None:
        """Delete a List for real via `deleteUserList`.

        GitHub's payload doesn't echo the deleted List's identity back
        (no `list` field on `DeleteUserListPayload`, confirmed via live
        introspection) — a non-error response is confirmation enough.
        """
        data = _graphql(_DELETE_LIST_MUTATION, listId=list_id)
        DeleteUserListResponse.model_validate(data)

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
        self.update_list_membership_for_node(node_id, list_ids)

    def update_list_membership_for_node(
        self, node_id: str, list_ids: list[str]
    ) -> None:
        """Same mutation as `update_list_membership_for_item`, given an
        already-resolved node ID — no extra round trip (ticket 16).
        """
        data = _graphql(
            _UPDATE_LIST_MEMBERSHIP_MUTATION, itemId=node_id, listIds=list_ids
        )
        payload = UpdateListsForItemResponse.model_validate(
            data
        ).update_user_lists_for_item
        if payload.item is None:
            raise GitHubApiError(
                f"updateUserListsForItem for node {node_id!r} returned no "
                "item (GitHub may not have applied the mutation)"
            )

    def resolve_repository_node_ids(self, full_names: list[str]) -> dict[str, str]:
        """Resolve several `full_name`s to node IDs in one aliased GraphQL
        request instead of one round trip per repo (ticket 16). GitHub's
        rate-limit points are charged by query complexity, not request
        count, so this saves round trips, not points — see
        docs/explanation/known-limitations.md.

        A `full_name` missing from the result was not found on GitHub
        (renamed/deleted since it was starred) and is simply omitted —
        not raised here, so one bad repo in a batch does not fail the
        whole lookup. The caller falls back to
        `_resolve_repository_node_id`'s per-item error for that repo.
        """
        if not full_names:
            return {}
        data = _graphql(_batched_repository_id_query(full_names))
        resolved: dict[str, str] = {}
        for index, full_name in enumerate(full_names):
            node = data.get(f"r{index}")
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                resolved[full_name] = cast(str, node["id"])
        return resolved

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
