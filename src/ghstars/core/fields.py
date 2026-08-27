"""Shared field-selection registry and rendering primitive (ticket 31 Scope D).

Before this module, three call sites each carried their own copy of "pick
these fields off a record, in this order": the CLI renderer
(`ghstars.cli._render_records`), the export writer
(`ghstars.core.export._star_records`), and four separate hardcoded
default-field lists (`list_lists.py`'s `DEFAULT_STAR_FIELDS` /
`DEFAULT_LISTS_FIELDS`, `retriage.py`'s `DEFAULT_RETRIAGE_FIELDS`,
`export.py`'s `DEFAULT_EXPORT_FIELDS`). This module replaces all of that
with one registry (`FIELD_REGISTRY`) and one selection helper
(`select_fields`).

## Registry shape

Each entry is a `FieldSet`: a `basic` tuple (today's default field list,
unchanged) and a `detailed` tuple (every field on the underlying model).
Ticket 30 consumes both -- `basic` is today's plain-text/default JSON
shape, `detailed` is what an opt-in `--details`-style flag would widen to.
This ticket only makes both sets exist and be correct; it adds no CLI flag.

Four keys, four record types:

- `"star"`      -- `ghstars.core.models.Star`, as rendered by `ghstars list`.
- `"list"`      -- `ghstars.core.models.List`, as rendered by `ghstars lists`.
- `"retriage"`  -- `ghstars.core.models.RetriageEntry`, as rendered by
                   `ghstars retriage`.
- `"export"`    -- `Star`, as selected by `ghstars.core.export.select_stars`
                   and written by `run_export`.

`"star"` and `"export"` both wrap the same model (`Star`) but keep separate
entries because their `basic` sets always disagreed (`ghstars list`'s
`full_name, language, stargazer_count` vs. export's
`full_name, html_url, description`) -- collapsing them would silently
change one surface's default output. Their `detailed` sets are identical
(`Star`'s full field list) since both ultimately dump a `Star`.

## Star vs. StarRow

Ticket 31 Scope A (`ghstars.core.discovery.query_stars`/`StarRow`) has not
landed on `main` yet at the time this ticket lands -- it is in flight in a
parallel worktree. `StarRow` is `Star` plus a resolved `list_names` field;
it does not exist as an importable model here. The `"star"`/`"export"`
entries in this registry are therefore defined against plain `Star`, not
`StarRow`.

When Scope A lands and ticket 30 wires `ghstars list` through
`query_stars()`, add a `"star_row"` entry here (or extend `"star"`'s
`detailed` set, if `StarRow` ends up field-compatible) whose `detailed`
tuple includes `list_names` -- `Star` itself carries no List-name field,
only `list_ids`, so a `Star`-only `detailed` set can never show List
membership by name. Do not guess at `StarRow`'s exact field layout here;
let ticket 30 add that entry once `StarRow` exists to introspect.
"""

from __future__ import annotations

from pydantic import BaseModel

from ghstars.core.models import List, RetriageEntry, Star


class FieldSet(BaseModel):
    """A record type's two supported field selections."""

    basic: tuple[str, ...]
    detailed: tuple[str, ...]


FIELD_REGISTRY: dict[str, FieldSet] = {
    "star": FieldSet(
        basic=("full_name", "language", "stargazer_count"),
        detailed=tuple(Star.model_fields.keys()),
    ),
    "list": FieldSet(
        basic=("name", "intent", "category", "is_private", "malformed"),
        detailed=tuple(List.model_fields.keys()),
    ),
    "retriage": FieldSet(
        basic=(
            "star_full_name",
            "attempted_list_ids",
            "conflict_detected_at",
            "resolved",
        ),
        detailed=tuple(RetriageEntry.model_fields.keys()),
    ),
    "export": FieldSet(
        basic=("full_name", "html_url", "description"),
        detailed=tuple(Star.model_fields.keys()),
    ),
}


def select_fields(
    record: BaseModel, fields: list[str] | tuple[str, ...] | None
) -> dict[str, object]:
    """Dump `record` to JSON-safe primitives, restricted to `fields`, in
    `fields`' own order. `fields=None` means no restriction: every field on
    `record`, in the model's own declared order (`model_dump`'s default).

    The one field-selection-plus-reorder helper the CLI renderer and the
    export writer both call. Replaces two near-identical implementations:
    `cli._render_records`'s `model_dump(include=...)` (which never
    reordered -- it followed the model's declared field order) and
    `export._star_records`'s `model_dump(include=...)` followed by a
    manual `{f: dumped[f] for f in fields}` reorder. Both now get the
    reorder: a caller-specified field order is honored consistently
    everywhere, not just in export.
    """
    if fields is None:
        return record.model_dump(mode="json")
    dumped = record.model_dump(mode="json", include=set(fields))
    return {f: dumped[f] for f in fields}
