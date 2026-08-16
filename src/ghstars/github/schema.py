"""Typed shapes for `gh api graphql` responses — the JSON boundary.

Parsing raw GraphQL JSON through these (rather than indexing dicts) gets
free validation of GitHub's response shape and keeps ghstars.github's own
code strictly typed, no Any leaking past this module.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict
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
    """`repository(owner, name) { id }` — resolves a full_name to GitHub's
    opaque node ID, needed as `removeStar`'s `starrableId` input (GraphQL
    mutations key on node ID, not `owner/repo`).
    """

    repository: NodeId | None = None


class RemoveStarPayload(_GraphQLModel):
    starrable: NodeId | None = None


class RemoveStarResponse(_GraphQLModel):
    remove_star: RemoveStarPayload
