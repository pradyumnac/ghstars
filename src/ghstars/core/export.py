"""Config-driven export engine (ticket 10).

Maps a List (or Category) to an output file + format, so the user can
drive their own downstream pipelines (`tools.yaml`, skill vendor lists)
without ghstars hardcoding any of those use cases. Per ADR 0002,
`~/.ghstars/config/` is TOML, plain-text, and git-diffable. `pyyaml` is
added only for the *output* side, to write a correct `tools.yaml`-shaped
file (`yaml.safe_dump` only -- ghstars never parses YAML, so the
historical `yaml.load`-on-untrusted-input class of issue does not apply
here).

Ticket 32 moved the *loading* of this schema into `ghstars.core.config`
(`load_core_config`, reading the `[export]` table of `ghstars.toml`) --
this module still owns the schema (`ExportConfig`/`ExportEntry`) and
every step downstream of a loaded config (`select_stars`, `run_export`),
just not the file read anymore.

An export entry selects a List either by exact name (`list_name = "..."`),
or by Category with an optional Intent filter (`category = "..."`,
`intent = "..."`), matching every List whose parsed Category (and, if
given, Intent) agrees. The latter is how a config aggregates across
intents for one Category, and how "what am I currently exploring but
haven't tried yet" (spec story 35) is expressed generically --
`category = "Vendored Skills"`, `intent = "Explore"` -- a config-driven
case, never a bespoke command.

A malformed List (`List.malformed=True`, ticket 03) is never matched by
either selector: `classify_list()` always leaves its `intent`/`category`
`None`, so a category-based selector cannot see it, and a list-based
selector only matches an *exact* GitHub-side name. What a naive
implementation could still get wrong is guessing: a malformed List whose
raw, unparsed `name` textually resembles what an entry is asking for
(e.g. `explore- Vendored Skills` against `category = "Vendored Skills"`).
Exporting it on that guess would violate the same principle ticket 03
already enforces at sync time -- never assign an Intent/Category via a
guess. `select_stars()` instead reports it back as skipped.
"""

import csv
import io
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

from ghstars.core.discovery import query_stars
from ghstars.core.fields import FIELD_REGISTRY, select_fields
from ghstars.core.models import Intent, List, Star
from ghstars.core.state_store import atomic_write

ExportFormat = Literal["yaml", "json", "csv"]

# Sourced from the shared field registry (ticket 31 Scope D) -- see
# `ghstars.core.fields.FIELD_REGISTRY["export"]`.
DEFAULT_EXPORT_FIELDS: tuple[str, ...] = FIELD_REGISTRY["export"].basic


class ExportEntry(BaseModel):
    """One config-driven mapping: a List or Category selector, plus the
    output file/format to write its Stars to.
    """

    name: str
    # Use `list_name` to avoid shadowing the built-in `list` in annotations.
    list_name: str | None = None
    category: str | None = None
    intent: Intent | None = None
    output: str
    format: ExportFormat
    # Fields default to the small, readable export set.
    fields: list[str] | None = None

    @model_validator(mode="after")
    def _check_selector(self) -> ExportEntry:
        if (self.list_name is None) == (self.category is None):
            raise ValueError(
                f"export {self.name!r}: set exactly one of `list_name` or "
                "`category`, not both or neither"
            )
        if self.list_name is not None and self.intent is not None:
            raise ValueError(
                f"export {self.name!r}: `intent` only applies alongside "
                "`category` -- a `list_name` selector's target List "
                "already encodes its own Intent in its name"
            )
        unknown = set(self.fields or []) - set(Star.model_fields)
        if unknown:
            raise ValueError(
                f"export {self.name!r}: unknown Star field(s): "
                f"{', '.join(sorted(unknown))}"
            )
        return self


class ExportConfig(BaseModel):
    exports: list[ExportEntry] = []


class ExportEntryResult(BaseModel):
    """What one `ExportEntry` did, for `ghstars export`'s report."""

    name: str
    output: str
    format: ExportFormat
    star_count: int
    # Report related malformed Lists without exporting them.
    skipped_malformed_lists: list[str] = []


def _matches(entry: ExportEntry, lst: List) -> bool:
    if lst.malformed:
        return False
    if entry.list_name is not None:
        return lst.name == entry.list_name
    return lst.category == entry.category and (
        entry.intent is None or lst.intent == entry.intent
    )


def _looks_related(entry: ExportEntry, lst: List) -> bool:
    """True when a malformed List's raw `name` textually resembles what
    `entry` is asking for. Used only to *report* a skip, never to select
    it into the export -- see module docstring.
    """
    needle = (entry.list_name or entry.category or "").casefold()
    return bool(needle) and needle in lst.name.casefold()


def select_stars(
    entry: ExportEntry, *, lists: list[List], stars: list[Star]
) -> tuple[list[Star], list[str]]:
    """Resolve one `ExportEntry` against synced Lists/Stars.

    Returns the matched Stars (sorted by `full_name`, for stable output
    across runs -- diffable in the user's own downstream git repo) and
    the names of any malformed Lists that looked related but were
    excluded (see module docstring).

    List-to-Star membership resolves through `Star.list_ids`, via
    `core.discovery.query_stars()`'s `list:<id>` Filter -- the same
    membership source `query_stars` (ticket 31 Scope A) already uses for
    the TUI and CLI. This used to scan `List.items` directly. `sync()`'s
    `reconcile_list_membership` (see `core/sync.py`) keeps `List.items`
    and every Star's `list_ids` in agreement, so the two sources usually
    match -- but "usually" is exactly the two-selection-paths bug ticket
    31 calls out (see the module docstring). `list_ids` is now the one
    source of truth; `export` selects through it like everything else.

    `query_stars`'s Filter grammar AND-combines Filters, so it cannot
    express "belongs to any of these Lists" (an OR across the matched
    Lists) in a single call -- one call is issued per matched List and
    the results are unioned here instead, deduped by `full_name`.
    `include_archived=True` is passed through so this keeps its
    historical behaviour of exporting Archived Stars (unlike the TUI/CLI
    query default) -- selection source changed, not what gets selected.
    """
    matched_lists = [lst for lst in lists if _matches(entry, lst)]
    skipped = sorted(
        {lst.name for lst in lists if lst.malformed and _looks_related(entry, lst)}
    )
    selected_by_name: dict[str, Star] = {}
    for lst in matched_lists:
        rows = query_stars(
            stars, lists, filters=[f"list:{lst.id}"], include_archived=True
        )
        for row in rows:
            selected_by_name[row.star.full_name] = row.star
    selected = sorted(selected_by_name.values(), key=lambda star: star.full_name)
    return selected, skipped


def _star_records(stars: list[Star], fields: list[str]) -> list[dict[str, object]]:
    return [select_fields(star, fields) for star in stars]


def _to_csv(records: list[dict[str, object]], fields: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()


def _serialize(
    records: list[dict[str, object]], fields: list[str], fmt: ExportFormat
) -> str:
    if fmt == "json":
        return json.dumps(records, indent=2) + "\n"
    if fmt == "yaml":
        # Preserve the configured field order in YAML output.
        return yaml.safe_dump(records, sort_keys=False, allow_unicode=True)
    return _to_csv(records, fields)


def run_export(
    config: ExportConfig, *, lists: list[List], stars: list[Star], base_dir: Path
) -> list[ExportEntryResult]:
    """Run every entry in `config`, writing its output file under
    `base_dir` (relative `output` paths resolve against it; an absolute
    or `~`-prefixed `output` is honored as-is -- e.g. a dotfiles repo
    elsewhere on disk).
    """
    results = []
    for entry in config.exports:
        selected, skipped = select_stars(entry, lists=lists, stars=stars)
        fields = entry.fields or list(DEFAULT_EXPORT_FIELDS)
        records = _star_records(selected, fields)
        content = _serialize(records, fields, entry.format)

        # Expand `~` before resolving relative output paths.
        output_path = Path(entry.output).expanduser()
        if not output_path.is_absolute():
            output_path = base_dir / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically so readers never see a partial export.
        atomic_write(output_path, content)

        results.append(
            ExportEntryResult(
                name=entry.name,
                output=str(output_path),
                format=entry.format,
                star_count=len(selected),
                skipped_malformed_lists=skipped,
            )
        )
    return results
