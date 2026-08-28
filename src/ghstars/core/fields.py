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

Five keys, four record types:

- `"star"`      -- `ghstars.core.models.Star`. Unused by any command as of
                   ticket 30 Scope 2 (`ghstars stars` moved to `"star_row"`
                   below); kept because `"export"` still wraps plain `Star`
                   and the two entries' history is worth keeping distinct.
- `"star_row"`  -- `StarRowFields` (`Star` plus resolved `list_names`), as
                   rendered by `ghstars stars` (ticket 30 Scope 2). Decision
                   16: basic is `full_name, list_names, starred_at,
                   stargazer_count`; detailed is every `Star` field plus
                   `list_names`.
- `"list"`      -- `ghstars.core.models.List`, as rendered by
                   `ghstars github-lists`. The registry key stays `"list"`
                   (it names the model, not the command; ticket 30 Scope 7
                   renamed the command, not this field-set registry).
- `"retriage"`  -- `ghstars.core.models.RetriageEntry`, as rendered by
                   `ghstars retriage`.
- `"export"`    -- `Star`, as selected by `ghstars.core.export.select_stars`
                   and written by `run_export`.

`"star"` and `"export"` both wrap the same model (`Star`) but keep separate
entries because their `basic` sets always disagreed (`ghstars stars`'s old
`full_name, language, stargazer_count` vs. export's
`full_name, html_url, description`) -- collapsing them would silently
change one surface's default output. Their `detailed` sets are identical
(`Star`'s full field list) since both ultimately dump a `Star`.

## Star vs. StarRow

`ghstars.core.discovery.StarRow` is a frozen dataclass pairing a `Star`
with `list_names`, deliberately not a field on `Star` itself (a query-time
join, not a persisted fact -- see that module's docstring). `select_fields`
needs a `BaseModel` to call `.model_dump()` on, so `StarRowFields` (defined
in this module) subclasses `Star` and adds `list_names`, purely as a
field-selectable view for the CLI layer. A caller builds one per `StarRow`
it renders: `StarRowFields(**row.star.model_dump(), list_names=row.list_names)`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ghstars.core.models import List, RetriageEntry, Star


class FieldSet(BaseModel):
    """A record type's two supported field selections."""

    basic: tuple[str, ...]
    detailed: tuple[str, ...]


class StarRowFields(Star):
    """`Star` plus its resolved `list_names`, flattened for field selection.

    `core.discovery.StarRow` deliberately keeps `list_names` off `Star`
    itself (see that module's docstring) -- it is a query-time join, not a
    persisted fact. This subclass exists only so `select_fields()` has one
    field-selectable record to hand `ghstars stars` (ticket 30 Scope 2),
    without adding a second field-selection code path or bolting the join
    onto the persisted model.
    """

    list_names: list[str] = Field(default_factory=list)


FIELD_REGISTRY: dict[str, FieldSet] = {
    "star": FieldSet(
        basic=("full_name", "language", "stargazer_count"),
        detailed=tuple(Star.model_fields.keys()),
    ),
    "star_row": FieldSet(
        # Decision 16 (ticket 30): full_name, list_names, starred_at,
        # stargazer_count. Detailed is every Star field plus list_names.
        basic=("full_name", "list_names", "starred_at", "stargazer_count"),
        detailed=(*Star.model_fields.keys(), "list_names"),
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
