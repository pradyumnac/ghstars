"""Parsing tests for ghstars.github.schema, against static JSON fixtures.

No network, no `gh` subprocess -- these feed already-captured response
shapes straight into `model_validate`, per the spec's testing rule that
only ghstars.core is unit-tested against live behavior via the fake
client. This module is the one exception: pure JSON-to-model parsing,
with no I/O, is safe and cheap to test directly.
"""

from ghstars.github.schema import (
    CreateUserListResponse,
    DeleteUserListResponse,
    FollowingResponse,
    OwnedReposResponse,
    RateLimitResponse,
    RemoveStarResponse,
    RepositoryIdResponse,
    StarredResponse,
    UpdateListsForItemResponse,
    UpdateUserListResponse,
    UserListItemsNodeResponse,
    UserListsResponse,
)


def test_starred_response_parses_aliases_and_language() -> None:
    data = {
        "viewer": {
            "starredRepositories": {
                "pageInfo": {"hasNextPage": True, "endCursor": "abc123"},
                "edges": [
                    {
                        "starredAt": "2026-08-16T00:22:48Z",
                        "node": {
                            "nameWithOwner": "gloom-sh/gloomberb",
                            "url": "https://github.com/gloom-sh/gloomberb",
                            "description": "Finance terminal, in your terminal.",
                            "primaryLanguage": {"name": "TypeScript"},
                            "licenseInfo": {"spdxId": "MIT", "name": "MIT License"},
                            "stargazerCount": 1763,
                        },
                    }
                ],
            }
        }
    }

    parsed = StarredResponse.model_validate(data)
    conn = parsed.viewer.starred_repositories
    assert conn.page_info.has_next_page is True
    assert conn.page_info.end_cursor == "abc123"
    node = conn.edges[0].node
    assert node.name_with_owner == "gloom-sh/gloomberb"
    assert node.primary_language is not None
    assert node.primary_language.name == "TypeScript"
    assert node.license_info is not None
    assert node.license_info.spdx_id == "MIT"
    assert node.stargazer_count == 1763


def test_starred_response_handles_null_language() -> None:
    data = {
        "viewer": {
            "starredRepositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "edges": [
                    {
                        "starredAt": "2026-08-16T00:22:48Z",
                        "node": {
                            "nameWithOwner": "kodustech/awesome-agent-skills",
                            "url": "https://github.com/kodustech/awesome-agent-skills",
                            "description": None,
                            "primaryLanguage": None,
                            "stargazerCount": 96,
                        },
                    }
                ],
            }
        }
    }

    node = (
        StarredResponse.model_validate(data).viewer.starred_repositories.edges[0].node
    )
    assert node.primary_language is None
    assert node.description is None


def test_owned_repos_response_parses_parent() -> None:
    data = {
        "viewer": {
            "repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{"parent": {"nameWithOwner": "LukeSmithxyz/st"}}],
            }
        }
    }

    node = OwnedReposResponse.model_validate(data).viewer.repositories.nodes[0]
    assert node.parent is not None
    assert node.parent.name_with_owner == "LukeSmithxyz/st"


def test_owned_repos_response_handles_null_parent() -> None:
    data = {
        "viewer": {
            "repositories": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{"parent": None}],
            }
        }
    }

    node = OwnedReposResponse.model_validate(data).viewer.repositories.nodes[0]
    assert node.parent is None


def test_following_response_parses_logins() -> None:
    data = {
        "viewer": {
            "following": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{"login": "alexellis"}],
            }
        }
    }

    nodes = FollowingResponse.model_validate(data).viewer.following.nodes
    assert [n.login for n in nodes] == ["alexellis"]


def test_user_lists_response_parses_all_fields() -> None:
    data = {
        "viewer": {
            "lists": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {
                        "id": "UL_kwDOAbc123",
                        "name": "Explore: Tool",
                        "slug": "explore-tool",
                        "description": None,
                        "isPrivate": False,
                    }
                ],
            }
        }
    }

    node = UserListsResponse.model_validate(data).viewer.lists.nodes[0]
    assert node.id == "UL_kwDOAbc123"
    assert node.name == "Explore: Tool"
    assert node.is_private is False


def test_user_list_items_node_response_parses_items() -> None:
    data = {
        "node": {
            "items": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{"nameWithOwner": "example-owner/ghstars"}],
            }
        }
    }

    parsed = UserListItemsNodeResponse.model_validate(data)
    assert parsed.node is not None
    item = parsed.node.items.nodes[0]
    assert item is not None
    assert item.name_with_owner == "example-owner/ghstars"


def test_user_list_items_node_response_handles_deleted_list() -> None:
    parsed = UserListItemsNodeResponse.model_validate({"node": None})
    assert parsed.node is None


def test_rate_limit_response_parses_remaining_and_limit() -> None:
    data = {"rateLimit": {"remaining": 4953, "limit": 5000}}

    parsed = RateLimitResponse.model_validate(data)
    assert parsed.rate_limit.remaining == 4953
    assert parsed.rate_limit.limit == 5000


def test_repository_id_response_parses_node_id() -> None:
    data = {"repository": {"id": "R_kgDOabc123"}}

    parsed = RepositoryIdResponse.model_validate(data)
    assert parsed.repository is not None
    assert parsed.repository.id == "R_kgDOabc123"


def test_repository_id_response_handles_missing_repo() -> None:
    parsed = RepositoryIdResponse.model_validate({"repository": None})
    assert parsed.repository is None


def test_remove_star_response_parses_starrable() -> None:
    data = {"removeStar": {"starrable": {"id": "R_kgDOabc123"}}}

    parsed = RemoveStarResponse.model_validate(data)
    assert parsed.remove_star.starrable is not None
    assert parsed.remove_star.starrable.id == "R_kgDOabc123"


def test_remove_star_response_handles_null_starrable() -> None:
    data = {"removeStar": {"starrable": None}}

    parsed = RemoveStarResponse.model_validate(data)
    assert parsed.remove_star.starrable is None


# These mutation fixtures use fields verified by GraphQL schema introspection.


def test_create_user_list_response_parses_list() -> None:
    data = {
        "createUserList": {
            "list": {
                "id": "UL_kwDOABkiBM4AhlIM",
                "name": "Explore: Tool",
                "slug": "explore-tool",
                "description": None,
                "isPrivate": False,
            }
        }
    }

    parsed = CreateUserListResponse.model_validate(data)
    assert parsed.create_user_list.list is not None
    assert parsed.create_user_list.list.id == "UL_kwDOABkiBM4AhlIM"
    assert parsed.create_user_list.list.name == "Explore: Tool"


def test_create_user_list_response_handles_null_list() -> None:
    data = {"createUserList": {"list": None}}

    parsed = CreateUserListResponse.model_validate(data)
    assert parsed.create_user_list.list is None


def test_update_lists_for_item_response_parses_typename() -> None:
    data = {"updateUserListsForItem": {"item": {"__typename": "Repository"}}}

    parsed = UpdateListsForItemResponse.model_validate(data)
    assert parsed.update_user_lists_for_item.item is not None
    assert parsed.update_user_lists_for_item.item.typename == "Repository"


def test_update_lists_for_item_response_handles_null_item() -> None:
    data = {"updateUserListsForItem": {"item": None}}

    parsed = UpdateListsForItemResponse.model_validate(data)
    assert parsed.update_user_lists_for_item.item is None


def test_update_user_list_response_parses_list() -> None:
    data = {
        "updateUserList": {
            "list": {
                "id": "UL_kwDOABkiBM4AhlIM",
                "name": "Explore: New",
                "slug": "explore-new",
                "description": None,
                "isPrivate": False,
            }
        }
    }

    parsed = UpdateUserListResponse.model_validate(data)
    assert parsed.update_user_list.list is not None
    assert parsed.update_user_list.list.id == "UL_kwDOABkiBM4AhlIM"
    assert parsed.update_user_list.list.name == "Explore: New"


def test_update_user_list_response_handles_null_list() -> None:
    data = {"updateUserList": {"list": None}}

    parsed = UpdateUserListResponse.model_validate(data)
    assert parsed.update_user_list.list is None


def test_delete_user_list_response_parses_client_mutation_id() -> None:
    data = {"deleteUserList": {"clientMutationId": "abc123"}}

    parsed = DeleteUserListResponse.model_validate(data)
    assert parsed.delete_user_list.client_mutation_id == "abc123"


def test_delete_user_list_response_handles_missing_client_mutation_id() -> None:
    data: dict[str, dict[str, str]] = {"deleteUserList": {}}

    parsed = DeleteUserListResponse.model_validate(data)
    assert parsed.delete_user_list.client_mutation_id is None
