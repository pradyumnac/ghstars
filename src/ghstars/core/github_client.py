from typing import Protocol

from ghstars.core.models import List, RateLimitStatus, Star


class GitHubClient(Protocol):
    """The one seam between ghstars.core and GitHub.

    ghstars.github implements this over `gh api graphql`; tests inject
    FakeGitHubClient instead. No other GitHub access path exists.
    """

    def fetch_stars(self) -> list[Star]: ...

    def fetch_lists(self) -> list[List]: ...

    def create_list(
        self, name: str, *, is_private: bool = False, description: str | None = None
    ) -> List: ...

    def update_list(
        self,
        list_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        is_private: bool | None = None,
    ) -> List: ...

    def delete_list(self, list_id: str) -> None: ...

    def update_list_membership_for_item(
        self, item_id: str, list_ids: list[str]
    ) -> None: ...

    def update_list_membership_for_node(
        self, node_id: str, list_ids: list[str]
    ) -> None:
        """Same mutation as `update_list_membership_for_item`, but `node_id`
        is already GitHub's opaque node ID — no `full_name` -> node ID
        resolution round trip. Lets a caller that already resolved several
        node IDs in one batch (`resolve_repository_node_ids`) skip the
        redundant per-item resolution `update_list_membership_for_item`
        does internally (ticket 16).
        """
        ...

    def resolve_repository_node_ids(self, full_names: list[str]) -> dict[str, str]:
        """Resolve several `full_name`s to GitHub's opaque node IDs in one
        batched request, instead of one round trip per repo (ticket 16 —
        the TUI's bulk-tag path uses this to halve its round-trip count;
        see docs/explanation/known-limitations.md).

        A `full_name` GitHub can't resolve (renamed/deleted since it was
        starred) is simply omitted from the returned mapping, not an
        error — the caller falls back to per-item resolution for that one
        repo, isolating the failure the same way a bulk push already does.
        """
        ...

    def remove_star(self, item_id: str) -> None:
        """Unstar the repo for real via GitHub's `removeStar` mutation.

        `item_id` is the Star's `full_name` (`owner/repo`), the same key
        `state_store` and `FakeGitHubClient` use. It is not GitHub's node
        ID. A concrete client must resolve `full_name` to a node ID itself.
        """
        ...

    def check_rate_limit(self) -> RateLimitStatus: ...
