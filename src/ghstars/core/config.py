"""`~/.ghstars/config/ghstars.toml` -- the core-tier config file (ticket 32).

Ticket 32 splits ghstars config into three tiers, one file per layer:

- Core concerns (settings `ghstars.core` and every layer above it share)
  live in `ghstars.toml`, loaded here.
- CLI concerns live in `cli.toml` (`ghstars.cli.deps.get_cli_config_path`).
- TUI concerns live in `tui.toml` (`ghstars.tui.config`, unchanged by this
  ticket -- ADR 0008's rule still governs the config/state split inside
  that one tier).

A setting lives in exactly one of these three files, never two. Apply
this test when a new setting needs a home: would every consumer of
`ghstars.core` want it (not just the CLI or just the TUI)? If yes, it is
core and belongs here. If only the CLI cares, it belongs in `cli.toml`.
If only the TUI cares, it belongs in `tui.toml`.

Today `ghstars.toml` holds one table: `[export]`, the export engine's
config (ticket 10). It reuses `ExportConfig`/`ExportEntry` unchanged --
only *where* export config is read from moved, not its shape.

Same loading rule the sibling tiers already follow (`load_tui_config`,
and the retired `load_export_config` before it): a missing file means
every default applies, never an error. ghstars never writes into
`config/` on the user's behalf (ADR 0002).
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from ghstars.core.export import ExportConfig


class CoreConfigError(Exception):
    """`~/.ghstars/config/ghstars.toml` is present but unparseable or
    fails validation.

    Raised at load time, before any file is written -- a bad config
    entry must never fall back to a guess (same principle ticket 03's
    malformed-List handling follows), it hard-fails via `fail()` in the
    CLI. Replaces the retired `ExportConfigError`: one file, one error
    type, covering every table `ghstars.toml` holds.
    """


class CoreConfig(BaseModel):
    """`ghstars.toml`'s schema. One table per core-tier concern.

    `export` reuses `ExportConfig` unchanged (ticket 10's schema) --
    ticket 32 only moved *where* it loads from, nesting it under the
    `[export]` table instead of its own `export.toml`.

    `extra="forbid"`, same as `TuiConfig`: an unknown top-level table is
    a typo, not a future extension point, and should surface at load
    time rather than silently vanish.
    """

    model_config = ConfigDict(extra="forbid")

    export: ExportConfig = ExportConfig()


def load_core_config(path: Path) -> CoreConfig:
    """Load and validate `ghstars.toml`. A missing file is every default
    -- same rule `load_tui_config` follows for `tui.toml`. A
    present-but-invalid file always raises `CoreConfigError` -- never
    silently ignored, never guessed at.
    """
    if not path.exists():
        return CoreConfig()
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise CoreConfigError(f"{path}: invalid TOML: {exc}") from exc
    try:
        return CoreConfig.model_validate(raw)
    except ValidationError as exc:
        raise CoreConfigError(f"{path}: invalid core config: {exc}") from exc
