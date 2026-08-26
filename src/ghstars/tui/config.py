"""TUI config foundation (ticket 21): `config/tui.toml` (read-only,
user-authored) and `state/tui-state.toml` (read + write, machine-owned).

Mirrors the load pattern `ghstars.core.export.load_export_config` already
established for `export.toml` (ADR 0002): a missing file means every
default applies, never an error.

Split per the spec's "TUI config: two files, split by who writes them"
note (spec.md, ADR 0002): `config/tui.toml` is stow-managed dotfiles --
this module never writes it, only reads it, applying overrides before the
first paint. `state/tui-state.toml` is machine-owned -- read at launch and
written at quit, holding at least the last View Mode, sort key, and
active Filter.

Uses `tomlkit`, not stdlib `tomllib`, because `tui-state.toml` must
round-trip (read, then later write back) -- `tomllib` has no writer, and
`tomllib` + `tomli_w` would not preserve formatting/comments the way
`tomlkit` does. `tui.toml` is read via `tomlkit` too, rather than stdlib
`tomllib`, only so a future config-editor ticket that writes `tui.toml`
(spec story 70) needs no second TOML dependency -- this ticket itself
still never writes `tui.toml`.
"""

from pathlib import Path

import tomlkit
from pydantic import BaseModel, Field, ValidationError
from tomlkit.exceptions import TOMLKitError

from ghstars.core.state_store import atomic_write

DEFAULT_HEADER_HEIGHT = 1
DEFAULT_ROW_HEIGHT = 1


class TuiConfigError(Exception):
    """`config/tui.toml` is present but unparseable or fails validation.

    Raised at load time -- a bad user-authored config must never fall
    back to a silent guess (same principle `ExportConfigError` follows),
    it should surface to the user so they can fix their dotfile.
    """


class TuiColours(BaseModel):
    """Colour palette overrides, keyed by the same names ghstars' own
    Textual CSS already uses ($primary, $background, etc, minus the
    `$`). An unset field falls back to Textual's own active theme, not a
    hardcoded ghstars default -- so a user who already themes their
    terminal/Textual app elsewhere is not fighting a second default.
    """

    primary: str | None = None
    background: str | None = None
    surface: str | None = None
    error: str | None = None
    text: str | None = None


class TuiConfig(BaseModel):
    """`config/tui.toml`'s schema. Read-only from this module's point of
    view -- ghstars never writes this file in this ticket (ADR 0002); a
    config-editor ticket writing it is future work (spec story 70).

    `keybindings` maps an action name (matching `TuiApp`'s existing
    `action_*` methods, e.g. `"tag_selected"`) to a replacement key, so
    an override composes with the static `BINDINGS` list already on
    `TuiApp` rather than replacing the mechanism -- see
    `TuiApp._apply_keybinding_overrides()`.
    """

    keybindings: dict[str, str] = {}
    header_height: int = Field(default=DEFAULT_HEADER_HEIGHT, ge=1)
    row_height: int = Field(default=DEFAULT_ROW_HEIGHT, ge=1)
    colours: TuiColours = TuiColours()


def load_tui_config(path: Path) -> TuiConfig:
    """Load and validate `tui.toml`. A missing file is every default,
    not an error -- same rule `load_export_config` follows for
    `export.toml`. A present-but-invalid file always raises
    `TuiConfigError` -- never silently ignored, never guessed at.
    """
    if not path.exists():
        return TuiConfig()
    try:
        raw = tomlkit.loads(path.read_text())
    except TOMLKitError as exc:
        raise TuiConfigError(f"{path}: invalid TOML: {exc}") from exc
    try:
        return TuiConfig.model_validate(raw)
    except ValidationError as exc:
        raise TuiConfigError(f"{path}: invalid TUI config: {exc}") from exc


class TuiState(BaseModel):
    """`state/tui-state.toml`'s schema -- session state ghstars remembers
    across launches (spec story 71).

    `view_mode` is a forward-compatible stub, not a real feature yet:
    there is no View Mode switcher in the code today (ticket 25 builds
    it). Today there is exactly one mode, `"list"`, and this field
    exists purely so ticket 25 has a state slot to read/write from
    without a second migration -- it is persisted and restored here,
    but nothing in this ticket lets the user change it.
    """

    view_mode: str = "list"
    sort_key: str | None = None
    filter: str | None = None
    detail_pane_visible: bool = True


def load_tui_state(path: Path) -> TuiState:
    """Load `tui-state.toml`. A missing file is every default -- same
    rule as `load_tui_config`/`load_export_config`. Unlike `tui.toml`,
    a present-but-invalid state file is not hand-authored config to
    fail loudly over -- it is ghstars' own machine-written file, so a
    corrupt one (e.g. from an interrupted write, or a schema change
    across an upgrade) falls back to defaults rather than blocking the
    TUI from launching at all.
    """
    if not path.exists():
        return TuiState()
    try:
        raw = tomlkit.loads(path.read_text())
        return TuiState.model_validate(raw)
    except TOMLKitError, ValidationError:
        return TuiState()


def save_tui_state(path: Path, state: TuiState) -> None:
    """Write `tui-state.toml` on quit.

    `None` fields (no sort key / no active Filter yet) are omitted
    rather than written as an empty string, so a freshly-written file
    round-trips through `load_tui_state()` back to the same `None`.
    Same atomic temp-file+rename guarantee as `StateStore`'s own writes
    (`ghstars.core.state_store.atomic_write`) -- a concurrent read, or a
    crash mid-write, must never see a truncated file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.document()
    for key, value in state.model_dump(mode="json").items():
        if value is not None:
            doc[key] = value
    atomic_write(path, tomlkit.dumps(doc))
