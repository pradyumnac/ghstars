"""Typed shapes for `gh api graphql` responses — the JSON boundary.

Parsing raw GraphQL JSON through these (rather than indexing dicts) gets
free validation of GitHub's response shape and keeps ghstars.github's own
code strictly typed, no Any leaking past this module.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _GraphQLModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PageInfo(_GraphQLModel):
    has_next_page: bool
    end_cursor: str | None = None


class Language(_GraphQLModel):
    name: str


class RepoParent(_GraphQLModel):
    name_with_owner: str


class StarredRepoNode(_GraphQLModel):
    name_with_owner: str
    url: str
    description: str | None = None
    primary_language: Language | None = None
    stargazer_count: int


class StarredEdge(_GraphQLModel):
    starred_at: datetime
    node: StarredRepoNode


class StarredConnection(_GraphQLModel):
    page_info: PageInfo
    edges: list[StarredEdge]


class StarredViewer(_GraphQLModel):
    starred_repositories: StarredConnection


class StarredResponse(_GraphQLModel):
    viewer: StarredViewer


class OwnedRepoNode(_GraphQLModel):
    parent: RepoParent | None = None


class OwnedReposConnection(_GraphQLModel):
    page_info: PageInfo
    nodes: list[OwnedRepoNode]


class OwnedReposViewer(_GraphQLModel):
    repositories: OwnedReposConnection


class OwnedReposResponse(_GraphQLModel):
    viewer: OwnedReposViewer


class FollowingNode(_GraphQLModel):
    login: str


class FollowingConnection(_GraphQLModel):
    page_info: PageInfo
    nodes: list[FollowingNode]


class FollowingViewer(_GraphQLModel):
    following: FollowingConnection


class FollowingResponse(_GraphQLModel):
    viewer: FollowingViewer


class RateLimit(_GraphQLModel):
    remaining: int
    limit: int


class RateLimitResponse(_GraphQLModel):
    rate_limit: RateLimit


class NodeId(_GraphQLModel):
    """Any GraphQL object that returns just its opaque node `id`."""

    id: str


class RepositoryIdResponse(_GraphQLModel):
    """`repository(owner, name) { id }` resolves a full_name to GitHub's
    opaque node ID. Needed as `removeStar`'s `starrableId` input.
    """

    repository: NodeId | None = None


class RemoveStarPayload(_GraphQLModel):
    starrable: NodeId | None = None


class RemoveStarResponse(_GraphQLModel):
    remove_star: RemoveStarPayload


class UserListNode(_GraphQLModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    is_private: bool


class UserListsConnection(_GraphQLModel):
    page_info: PageInfo
    nodes: list[UserListNode]


class UserListsViewer(_GraphQLModel):
    lists: UserListsConnection


class UserListsResponse(_GraphQLModel):
    viewer: UserListsViewer


class RepositoryItemNode(_GraphQLModel):
    # None if `... on Repository` does not match. Should not happen —
    # UserListItems only resolves to Repository (confirmed via
    # introspection) — but the schema marks the field nullable.
    name_with_owner: str | None = None


class UserListItemsConnection(_GraphQLModel):
    page_info: PageInfo
    nodes: list[RepositoryItemNode | None]


class UserListItemsOnly(_GraphQLModel):
    items: UserListItemsConnection


class UserListItemsNodeResponse(_GraphQLModel):
    # `node` is None if the list ID no longer resolves (e.g. deleted
    # between the outer `viewer.lists` fetch and this per-list item fetch).
    node: UserListItemsOnly | None = None


class CreateUserListPayload(_GraphQLModel):
    list: UserListNode | None = None


class CreateUserListResponse(_GraphQLModel):
    create_user_list: CreateUserListPayload


class TypedNode(_GraphQLModel):
    """A node queried for just `__typename`, to confirm a union isn't null."""

    typename: str = Field(alias="__typename")


class UpdateListsForItemPayload(_GraphQLModel):
    item: TypedNode | None = None


class UpdateListsForItemResponse(_GraphQLModel):
    update_user_lists_for_item: UpdateListsForItemPayload


class UpdateUserListPayload(_GraphQLModel):
    list: UserListNode | None = None


class UpdateUserListResponse(_GraphQLModel):
    update_user_list: UpdateUserListPayload


class DeleteUserListPayload(_GraphQLModel):
    # GitHub's schema returns `user`/`clientMutationId` here, not the
    # deleted List's identity -- nothing further to validate beyond a
    # non-error response (confirmed via live introspection, ticket 07).
    client_mutation_id: str | None = None


class DeleteUserListResponse(_GraphQLModel):
    delete_user_list: DeleteUserListPayload
