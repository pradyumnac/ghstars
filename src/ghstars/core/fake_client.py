import uuid

from ghstars.core.models import List, RateLimitStatus, Star


class FakeGitHubClient:
    """In-memory GitHubClient double. No network access, ever."""

    def __init__(
        self,
        stars: list[Star] | None = None,
        lists: list[List] | None = None,
        rate_limit: RateLimitStatus | None = None,
    ) -> None:
        self._stars: dict[str, Star] = {s.full_name: s for s in (stars or [])}
        self._lists: dict[str, List] = {lst.id: lst for lst in (lists or [])}
        self._rate_limit = rate_limit or RateLimitStatus(
            remaining=5000, limit=5000, ok=True
        )

    def fetch_stars(self) -> list[Star]:
        # pending_list_ids is purely local (ghstars.core.tagging's stage
        # for an unpushed edit) -- no GitHubClient's fetch_stars can ever
        # return it, real or fake, same as RealGitHubClient always
        # constructing a fresh Star() that never sets the field.
        return [
            star.model_copy(update={"pending_list_ids": None})
            for star in self._stars.values()
        ]

    def fetch_lists(self) -> list[List]:
        return list(self._lists.values())

    def create_list(
        self, name: str, *, is_private: bool = False, description: str | None = None
    ) -> List:
        list_id = f"L_{uuid.uuid4().hex[:8]}"
        created = List(
            id=list_id,
            name=name,
            slug=name.lower().replace(" ", "-").replace(":", ""),
            description=description,
            is_private=is_private,
        )
        self._lists[list_id] = created
        return created

    def update_list(
        self,
        list_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        is_private: bool | None = None,
    ) -> List:
        existing = self._lists[list_id]
        updated = existing.model_copy(
            update={
                k: v
                for k, v in {
                    "name": name,
                    "description": description,
                    "is_private": is_private,
                }.items()
                if v is not None
            }
        )
        self._lists[list_id] = updated
        return updated

    def delete_list(self, list_id: str) -> None:
        del self._lists[list_id]
        for full_name, star in self._stars.items():
            if list_id in star.list_ids:
                self._stars[full_name] = star.model_copy(
                    update={"list_ids": [i for i in star.list_ids if i != list_id]}
                )

    def update_list_membership_for_item(
        self, item_id: str, list_ids: list[str]
    ) -> None:
        self._update_membership(item_id, list_ids)

    def update_list_membership_for_node(
        self, node_id: str, list_ids: list[str]
    ) -> None:
        # No separate node-ID space in this fake -- full_name doubles as
        # the "node ID" everywhere else in this class (see
        # resolve_repository_node_ids below). Kept as its own method
        # (not a call to update_list_membership_for_item) so a test can
        # override one without silently affecting the other, same as the
        # real client's two distinct methods.
        self._update_membership(node_id, list_ids)

    def _update_membership(self, item_id: str, list_ids: list[str]) -> None:
        star = self._stars[item_id]
        previous_ids = set(star.list_ids)
        new_ids = set(list_ids)
        self._stars[item_id] = star.model_copy(update={"list_ids": list(list_ids)})

        for list_id in previous_ids - new_ids:
            lst = self._lists[list_id]
            self._lists[list_id] = lst.model_copy(
                update={"items": [i for i in lst.items if i != item_id]}
            )
        for list_id in new_ids - previous_ids:
            lst = self._lists[list_id]
            self._lists[list_id] = lst.model_copy(
                update={"items": [*lst.items, item_id]}
            )

    def resolve_repository_node_ids(self, full_names: list[str]) -> dict[str, str]:
        # Identity map for every known Star; a full_name this fake has
        # never heard of is simply omitted, same contract as the real
        # client for a renamed/deleted repo.
        return {name: name for name in full_names if name in self._stars}

    def remove_star(self, item_id: str) -> None:
        star = self._stars.pop(item_id)
        for list_id in star.list_ids:
            lst = self._lists[list_id]
            self._lists[list_id] = lst.model_copy(
                update={"items": [i for i in lst.items if i != item_id]}
            )

    def check_rate_limit(self) -> RateLimitStatus:
        return self._rate_limit
