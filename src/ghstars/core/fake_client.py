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
        return list(self._stars.values())

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

    def remove_star(self, item_id: str) -> None:
        star = self._stars.pop(item_id)
        for list_id in star.list_ids:
            lst = self._lists[list_id]
            self._lists[list_id] = lst.model_copy(
                update={"items": [i for i in lst.items if i != item_id]}
            )

    def check_rate_limit(self) -> RateLimitStatus:
        return self._rate_limit
