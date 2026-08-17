"""Config-driven export engine (ticket 10).

Maps a List (or Category) to an output file + format, so the user can
drive their own downstream pipelines (`tools.yaml`, skill vendor lists)
without ghstars hardcoding any of those use cases. Per ADR 0002,
`~/.ghstars/config/` is TOML, plain-text, and git-diffable -- read here via
the stdlib `tomllib` (Python 3.11+), so the config side needs no new
dependency. `pyyaml` is added only for the *output* side, to write a
correct `tools.yaml`-shaped file (`yaml.safe_dump` only -- ghstars never
parses YAML, so the historical `yaml.load`-on-untrusted-input class of
issue does not apply here).

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
import tomllib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError, model_validator

from ghstars.core.models import Intent, List, Star
from ghstars.core.state_store import atomic_write

ExportFormat = Literal["yaml", "json", "csv"]

DEFAULT_EXPORT_FIELDS: tuple[str, ...] = ("full_name", "html_url", "description")


class ExportConfigError(Exception):
    """`~/.ghstars/config/export.toml` is unparseable or fails validation.

    Raised at load time, before any file is written -- a bad config
    entry must never fall back to a guess (same principle as ticket 03's
    malformed-List handling), it hard-fails via `fail()` in the CLI.
    """


class ExportEntry(BaseModel):
    """One config-driven mapping: a List or Category selector, plus the
    output file/format to write its Stars to.
    """

    name: str
    # Named `list_name`, not `list` -- a field named `list` shadows the
    # builtin `list` type used below in `fields: list[str] | None`, which
    # breaks Python 3.14's lazy annotation evaluation (PEP 649): pydantic
    # evaluates `list[str]` against a namespace that already binds `list`
    # to this field, not the builtin, and blows up constructing the model.
    list_name: str | None = None
    category: str | None = None
    intent: Intent | None = None
    output: str
    format: ExportFormat
    # Star fields to include, in order. Defaults to DEFAULT_EXPORT_FIELDS
    # -- deliberately not every Star field, so a plain `tools.yaml` stays
    # readable without the caller enumerating fields for the common case.
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
    # Malformed Lists that looked related to this entry's selector but
    # were never included -- see module docstring. Empty in the common
    # case; surfaced so the user can go rename the List (ticket 03).
    skipped_malformed_lists: list[str] = []


def load_export_config(path: Path) -> ExportConfig:
    """Load and validate `export.toml`. A missing file is empty config,
    not an error -- `ensure_config_dir()` scaffolds the directory but no
    file inside it (ADR 0002), same as no Lists synced yet elsewhere in
    the CLI. A present-but-invalid file always raises `ExportConfigError`
    -- never silently ignored, never guessed at.
    """
    if not path.exists():
        return ExportConfig()
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ExportConfigError(f"{path}: invalid TOML: {exc}") from exc
    try:
        return ExportConfig.model_validate(raw)
    except ValidationError as exc:
        raise ExportConfigError(f"{path}: invalid export config: {exc}") from exc


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
    """
    matched_lists = [lst for lst in lists if _matches(entry, lst)]
    skipped = sorted(
        {lst.name for lst in lists if lst.malformed and _looks_related(entry, lst)}
    )
    item_names = {name for lst in matched_lists for name in lst.items}
    selected = sorted(
        (star for star in stars if star.full_name in item_names),
        key=lambda star: star.full_name,
    )
    return selected, skipped


def _star_records(stars: list[Star], fields: list[str]) -> list[dict[str, object]]:
    records = []
    for star in stars:
        dumped = star.model_dump(mode="json", include=set(fields))
        records.append({f: dumped[f] for f in fields})
    return records


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
        # safe_dump only -- see module docstring. sort_keys=False keeps
        # each record in `fields` order rather than alphabetized.
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

        # expanduser() first: `~/repos/dotfiles/tools.yaml` is not
        # is_absolute() until `~` is expanded, so an unexpanded `~`
        # would otherwise be joined onto base_dir as a literal
        # directory named "~" instead of resolving to the home dir.
        output_path = Path(entry.output).expanduser()
        if not output_path.is_absolute():
            output_path = base_dir / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Same temp-file+rename guarantee as StateStore's own writes
        # (ghstars.core.state_store.atomic_write) -- a downstream
        # pipeline reading this file must never see a truncated one.
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
