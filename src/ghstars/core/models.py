from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Intent = Literal["Explore", "Current", "Retired", "Reference"]


class Star(BaseModel):
    full_name: str
    html_url: str
    description: str | None = None
    starred_at: datetime
    first_seen: datetime
    language: str | None = None
    stargazer_count: int = 0
    fork: bool = False
    follow: bool = False
    archived: bool = False
    archived_at: datetime | None = None
    last_checked: datetime
    list_ids: list[str] = []
    # Preserve staged membership edits for sync-time conflict arbitration.
    pending_list_ids: list[str] | None = None


class List(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    is_private: bool = False
    intent: Intent | None = None
    category: str | None = None
    # Flag attempted but invalid `{Intent}: {Category}` names without guessing.
    malformed: bool = False
    items: list[str] = []


class RetriageEntry(BaseModel):
    star_full_name: str
    attempted_list_ids: list[str]
    conflict_detected_at: datetime
    resolved: bool = False


class Nudge(BaseModel):
    slug: str
    theme: str
    message: str
    count: int = 1
    last_seen: datetime | None = None


class RateLimitStatus(BaseModel):
    remaining: int
    limit: int
    ok: bool
