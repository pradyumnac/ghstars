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

    def remove_star(self, item_id: str) -> None: ...

    def check_rate_limit(self) -> RateLimitStatus: ...
