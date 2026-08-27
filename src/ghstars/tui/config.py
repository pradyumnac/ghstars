"""The TUI's two files: `config/tui.toml` (user-authored) and
`state/tui-state.toml` (machine-owned).

ADR 0008 splits them. A value the user wants under version control, or
the same on every machine, is config. A value that records what the user
last looked at is state. One fact never lives in both files.

A missing file means every default applies, never an error -- the rule
`ghstars.core.config.load_core_config` already follows for
`ghstars.toml` (ADR 0002).

Uses `tomlkit`, not stdlib `tomllib`, because both files must round-trip
through a writer: `tui-state.toml` on every quit, and `tui.toml` when the
config editor saves. `tomllib` has no writer, and `tomllib` plus
`tomli_w` would not keep the comments and key order that a stow-managed
dotfile needs.
"""

from pathlib import Path
from typing import Literal

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from textual.binding import Binding, InvalidBinding
from textual.keys import Keys
from tomlkit.exceptions import TOMLKitError

from ghstars.core.state_store import atomic_write

DEFAULT_HEADER_HEIGHT = 1
DEFAULT_ROW_HEIGHT = 1
DEFAULT_DATE_FORMAT = "%d-%b-%Y"
DEFAULT_TOAST_TIMEOUT = 8
DEFAULT_DETAIL_PANE_HEIGHT = 14

# ADR 0008: four App-level keys stay fixed. `ctrl+c` is a terminal
# convention, `ctrl+q` is the force-quit path, and `ctrl+p` opens the
# command palette. `g` opens the config editor directly.
RESERVED_KEYS: dict[str, str] = {
    "ctrl+c": "the terminal's own interrupt convention",
    "ctrl+q": "the force-quit path",
    "ctrl+p": "the command palette path to the config editor",
    "g": "the direct config editor shortcut",
}

# Every key name Textual normalizes a single printable character to
# (`t`, `slash`, `plus`, ...), plus its own named keys (`escape`, `f5`,
# `pageup`, ...). A base key outside this set is a typo, not a key.
_MODIFIERS = frozenset({"ctrl", "shift", "alt", "meta", "super", "hyper"})
_KEY_NAMES = frozenset(
    [key.value for key in Keys]
    + [
        next(iter(Binding.make_bindings([Binding(chr(code), "", "")]))).key
        for code in range(33, 127)
        # A comma separates two keys, so it is never a key itself.
        if chr(code) != ","
    ]
)


def normalize_key(raw_key: str) -> str:
    """Normalize a `tui.toml` key string the way `TuiApp` binds it.

    Runs the same `Binding.make_bindings` pass
    `TuiApp._apply_keybinding_overrides` applies, and keeps its
    first-key-wins behaviour for a comma list, so validation can never
    pass a key the runtime then binds differently. Raises `ValueError`
    on a key string Textual cannot parse.
    """
    try:
        key = next(iter(Binding.make_bindings([Binding(raw_key, "", "")]))).key
    except InvalidBinding as exc:
        raise ValueError(f"{raw_key!r} is not a key: {exc}") from exc
    if key in _KEY_NAMES:
        return key
    *modifiers, base = key.split("+")
    unknown = [modifier for modifier in modifiers if modifier not in _MODIFIERS]
    if unknown:
        raise ValueError(f"{raw_key!r} is not a key: unknown modifier {unknown[0]!r}")
    if base not in _KEY_NAMES:
        raise ValueError(f"{raw_key!r} is not a key: unknown key {base!r}")
    return key


# The canonical action-to-key map (ADR 0008: 17 rebindable actions).
# It lives here, not on `TuiApp`, because `app.py` already imports this
# module -- validation needs the defaults to spot a collision with a key
# the user never touched, and reading them off `TuiApp` would make the
# two modules import each other. `TuiApp.BINDINGS` builds itself from
# this map, so there is still one source of truth for a default key.
DEFAULT_KEYBINDINGS: dict[str, str] = {
    "quit": "q",
    "tag_selected": "t",
    "toggle_detail_pane": "d",
    "toggle_select": "space",
    "select_all": "a",
    "clear_selection": "c",
    "show_lists": "l",
    "open_filter": "f",
    "clear_discovery": "x",
    "cycle_layout": "z",
    "open_in_browser": "o",
    "unstar_selected": "u",
    "cycle_sort": "s",
    "open_search": "slash",
    "close_search": "escape",
    "refresh_rate_limit": "r",
    "sync": "y",
}

LayoutDensity = Literal["compact", "balanced"]
# The fixed Category colour set (ADR 0008, ticket 23 Scope 2). A named
# colour, not a Textual semantic text role and not a raw hex: a role
# offers four values that read as one theme accent, and a raw hex lets
# the user author an illegible one.
CategoryColourName = Literal[
    "red",
    "orange",
    "yellow",
    "green",
    "cyan",
    "blue",
    "magenta",
    "violet",
]

# One hex per colour per theme polarity. No single hex clears 3:1 on both
# of Textual's own backgrounds: a light theme bottoms out at #D0D0D0
# (relative luminance 0.60) and a dark theme tops out at #242F38 (0.028),
# and those two limits leave no overlapping band. `app.py` selects the
# table that matches the active theme.
#
# WCAG 2.1 contrast against the worst-case background of each polarity --
# light `$panel` #D0D0D0 and dark `$panel` #242F38:
#
# | Colour  | Light hex | vs #D0D0D0 | Dark hex | vs #242F38 |
# | ------- | --------- | ---------- | -------- | ---------- |
# | red     | #B3261E   | 4.24       | #FF8A80  | 5.98       |
# | orange  | #8F4700   | 4.44       | #FFB870  | 8.02       |
# | yellow  | #6E5600   | 4.55       | #EBD26A  | 9.07       |
# | green   | #1F6B36   | 4.24       | #7FD69A  | 7.79       |
# | cyan    | #00595F   | 5.25       | #5FD6DC  | 7.89       |
# | blue    | #1A56C4   | 4.29       | #8AB4FF  | 6.53       |
# | magenta | #A81E80   | 4.31       | #F79AD9  | 6.88       |
# | violet  | #5B3FCB   | 4.51       | #B9A6FF  | 6.47       |
#
# Every value clears 3:1 on the other backgrounds of its polarity too
# (#FFFFFF and #E0E0E0; #121212 and #1E1E1E). `test_tui_config.py`
# recomputes the whole table, so an edit that breaks the guarantee fails.
CATEGORY_COLOURS_LIGHT: dict[CategoryColourName, str] = {
    "red": "#B3261E",
    "orange": "#8F4700",
    "yellow": "#6E5600",
    "green": "#1F6B36",
    "cyan": "#00595F",
    "blue": "#1A56C4",
    "magenta": "#A81E80",
    "violet": "#5B3FCB",
}
CATEGORY_COLOURS_DARK: dict[CategoryColourName, str] = {
    "red": "#FF8A80",
    "orange": "#FFB870",
    "yellow": "#EBD26A",
    "green": "#7FD69A",
    "cyan": "#5FD6DC",
    "blue": "#8AB4FF",
    "magenta": "#F79AD9",
    "violet": "#B9A6FF",
}

# Every optional column, in the order ticket 23 lists them. The Sel
# column and the Star column always show, so neither appears here.
ColumnName = Literal[
    "Owner",
    "Language",
    "License",
    "Stars",
    "Starred at",
    "First seen",
    "Membership",
    "Fork",
    "Follow",
    "Archived",
    "Archived at",
    "Last checked",
]


class TuiConfigError(Exception):
    """`config/tui.toml` is present but unparseable or fails validation.

    Raised at load time -- a bad user-authored config must never fall
    back to a silent guess (same principle `CoreConfigError` follows),
    it should surface to the user so they can fix their dotfile.
    """


class LayoutPreset(BaseModel):
    """One named density. `columns` is ordered -- the list sets which
    optional columns show and in what order (ADR 0008).

    Sizing lives here rather than at the top level so that switching
    preset with `z` switches every sizing choice at once.
    """

    columns: list[ColumnName] = Field(default_factory=list)
    detail_pane_visible: bool = True
    row_height: int = Field(default=DEFAULT_ROW_HEIGHT, ge=1)
    detail_pane_height: int = Field(default=DEFAULT_DETAIL_PANE_HEIGHT, ge=1)


DEFAULT_LAYOUTS: dict[LayoutDensity, LayoutPreset] = {
    "compact": LayoutPreset(columns=["Language", "Stars", "Membership"]),
    "balanced": LayoutPreset(
        columns=[
            "Language",
            "Stars",
            "Membership",
            "License",
            "Owner",
            "Starred at",
        ]
    ),
}


class TuiConfig(BaseModel):
    """`config/tui.toml`'s schema.

    ADR 0008's test for a new field: a value the user wants under version
    control, or the same on every machine, is config and belongs here. A
    value that records what the user last looked at is state and belongs
    in `TuiState`. One fact never lives in both files.

    A definition and an active selection are two different facts. This
    class defines the layout presets; `TuiState` records which preset is
    active. That is not a duplicate.

    ghstars applies this file once, at launch. A saved change takes
    effect on the next launch, because `_apply_keybinding_overrides` is
    not idempotent (ADR 0008).

    `keybindings` maps an action name (matching `TuiApp`'s existing
    `action_*` methods, e.g. `"tag_selected"`) to a replacement key, so
    an override composes with the static `BINDINGS` list already on
    `TuiApp` rather than replacing the mechanism -- see
    `TuiApp._apply_keybinding_overrides()`. An override is validated at
    load time against `DEFAULT_KEYBINDINGS` -- see `_check_keybindings`.
    A modal screen's own keys are not in that map, so `escape` and the
    modal navigation keys stay fixed (ADR 0008).
    """

    model_config = ConfigDict(extra="forbid")

    keybindings: dict[str, str] = Field(default_factory=dict)
    header_height: int = Field(default=DEFAULT_HEADER_HEIGHT, ge=1)
    show_clock: bool = False
    category_colours: dict[str, CategoryColourName] = Field(default_factory=dict)
    date_format: str = DEFAULT_DATE_FORMAT
    toast_timeout: int = Field(default=DEFAULT_TOAST_TIMEOUT, ge=1)
    ascii_only: bool = False
    default_filter: str | None = None
    layout: LayoutDensity = "compact"
    layouts: dict[LayoutDensity, LayoutPreset] = Field(
        default_factory=lambda: {
            name: preset.model_copy(deep=True)
            for name, preset in DEFAULT_LAYOUTS.items()
        }
    )

    @model_validator(mode="after")
    def _fill_unnamed_presets(self) -> TuiConfig:
        """A file that defines one preset keeps the shipped value for the
        other. A partial config must never blank a layout."""
        for name, preset in DEFAULT_LAYOUTS.items():
            self.layouts.setdefault(name, preset.model_copy(deep=True))
        return self

    @model_validator(mode="after")
    def _check_keybindings(self) -> TuiConfig:
        """Reject a keybinding the TUI cannot honour (ADR 0008).

        The duplicate check runs against the merged map -- the defaults
        with the user's overrides on top -- so an override that lands on
        a default key the user never moved fails too.
        """
        merged = {
            action: normalize_key(key) for action, key in DEFAULT_KEYBINDINGS.items()
        }
        for action, raw_key in self.keybindings.items():
            if action not in DEFAULT_KEYBINDINGS:
                known = ", ".join(sorted(DEFAULT_KEYBINDINGS))
                raise ValueError(
                    f"keybindings.{action}: unknown action; "
                    f"the rebindable actions are {known}"
                )
            key = normalize_key(raw_key)
            reason = RESERVED_KEYS.get(key)
            if reason is not None:
                raise ValueError(
                    f"keybindings.{action}: {key!r} is a reserved key "
                    f"({reason}); it cannot be rebound"
                )
            merged[action] = key
        owners: dict[str, str] = {}
        for action, key in merged.items():
            owner = owners.get(key)
            if owner is not None:
                raise ValueError(
                    f"keybindings: {key!r} is bound to two actions, "
                    f"{owner} and {action}"
                )
            owners[key] = action
        return self

    @property
    def active_layout(self) -> LayoutPreset:
        return self.layouts[self.layout]


def load_tui_config(path: Path) -> TuiConfig:
    """Load and validate `tui.toml`. A missing file is every default,
    not an error -- same rule `load_core_config` follows for
    `ghstars.toml`. A present-but-invalid file always raises
    `TuiConfigError` -- never silently ignored, never guessed at.
    """
    if not path.exists():
        return TuiConfig()
    try:
        raw = tomlkit.loads(path.read_text())
    except TOMLKitError as exc:
        raise TuiConfigError(f"{path}: invalid TOML: {exc}") from exc
    if "colours" in raw:
        raise TuiConfigError(
            f"{path}: the [colours] table was removed. ghstars no longer ships"
            " an application palette; the TUI uses the active Textual theme."
            " Delete the table."
        )
    if "grid_card_truncation" in raw:
        raise TuiConfigError(
            f"{path}: grid_card_truncation was removed because ghstars has no "
            "grid view. Delete the field."
        )
    try:
        return TuiConfig.model_validate(raw)
    except ValidationError as exc:
        raise TuiConfigError(f"{path}: invalid TUI config: {exc}") from exc


class TuiState(BaseModel):
    """`state/tui-state.toml`'s schema -- session state ghstars remembers
    across launches (spec story 71).

    ADR 0008's test for a new field: a value that records what the user
    last looked at is state and belongs here. A value the user wants
    under version control, or the same on every machine, is config and
    belongs in `TuiConfig`. One fact never lives in both files.

    `layout` records which preset is active now. `TuiConfig` defines the
    presets. `detail_pane_visible` is a session override of the active
    preset's value; a layout switch resets it.
    """

    sort_key: str | None = None
    filter: str | None = None
    detail_pane_visible: bool | None = None
    layout: LayoutDensity | None = None


def load_tui_state(path: Path) -> TuiState:
    """Load `tui-state.toml`. A missing file is every default -- same
    rule as `load_tui_config`/`load_core_config`. Unlike `tui.toml`,
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
