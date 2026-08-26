"""Tests for the TUI config schema: `config/tui.toml` (read-only) and
`state/tui-state.toml` (read + written), plus their wiring into
`TuiApp`.

Ticket 23 and ADR 0008 set the current schema. Config defines the layout
presets; state records which preset is active. The two files never hold
the same fact.
"""

from pathlib import Path

from conftest import StarFactory
from textual.widgets import DataTable, Static
from textual.widgets._data_table import RowKey

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.state_store import StateStore
from ghstars.tui.app import TuiApp
from ghstars.tui.config import (
    DEFAULT_LAYOUTS,
    LayoutPreset,
    TuiConfig,
    TuiConfigError,
    TuiState,
    load_tui_config,
    load_tui_state,
    save_tui_state,
)


def _table(app: TuiApp) -> DataTable[str]:
    return app.query_one("#stars-table", DataTable)


# -- load_tui_config ---------------------------------------------------


def test_load_tui_config_missing_file_is_every_default(tmp_path: Path) -> None:
    config = load_tui_config(tmp_path / "tui.toml")

    assert config == TuiConfig()
    assert config.keybindings == {}
    assert config.header_height == 1
    assert config.layout == "compact"
    assert config.date_format == "%d-%b-%Y"
    assert config.toast_timeout == 8
    assert config.ascii_only is False
    assert config.show_clock is False
    assert config.grid_card_truncation == 120
    assert config.default_filter is None
    assert config.layouts["compact"].row_height == 1
    assert config.layouts["compact"].detail_pane_visible is True
    assert config.layouts["compact"].detail_pane_height == 14
    assert config.layouts["balanced"].columns == DEFAULT_LAYOUTS["balanced"].columns
    assert not hasattr(config, "colours")
    assert not hasattr(config, "row_height")


def test_load_tui_config_reads_overrides(tmp_path: Path) -> None:
    path = tmp_path / "tui.toml"
    path.write_text(
        """
        header_height = 3
        layout = "balanced"
        date_format = "%Y-%m-%d"
        toast_timeout = 3
        ascii_only = true
        show_clock = true
        grid_card_truncation = 80
        default_filter = "unclassified"

        [keybindings]
        tag_selected = "shift+t"

        [layouts.compact]
        columns = ["Language", "Stars"]
        row_height = 2
        detail_pane_visible = false
        detail_pane_height = 9
        """
    )

    config = load_tui_config(path)

    assert config.header_height == 3
    assert config.layout == "balanced"
    assert config.date_format == "%Y-%m-%d"
    assert config.toast_timeout == 3
    assert config.ascii_only is True
    assert config.show_clock is True
    assert config.grid_card_truncation == 80
    assert config.default_filter == "unclassified"
    assert config.keybindings == {"tag_selected": "shift+t"}
    assert config.layouts["compact"] == LayoutPreset(
        columns=["Language", "Stars"],
        row_height=2,
        detail_pane_visible=False,
        detail_pane_height=9,
    )


def test_load_tui_config_unnamed_preset_keeps_its_default(tmp_path: Path) -> None:
    """A file that defines only `compact` still gets the shipped
    `balanced` preset, so a partial config never blanks a layout."""
    path = tmp_path / "tui.toml"
    path.write_text('[layouts.compact]\ncolumns = ["Stars"]\n')

    config = load_tui_config(path)

    assert config.layouts["compact"].columns == ["Stars"]
    assert config.layouts["balanced"] == DEFAULT_LAYOUTS["balanced"]


def test_load_tui_config_rejects_removed_colours_table(tmp_path: Path) -> None:
    """ADR 0008 removed `[colours]`. The error must name the table and
    point the user at the active Textual theme."""
    path = tmp_path / "tui.toml"
    path.write_text('[colours]\nprimary = "#ff00ff"\n')

    try:
        load_tui_config(path)
    except TuiConfigError as exc:
        assert "colours" in str(exc)
        assert "theme" in str(exc).lower()
    else:
        raise AssertionError("expected TuiConfigError")


def test_load_tui_config_rejects_unknown_column_name(tmp_path: Path) -> None:
    path = tmp_path / "tui.toml"
    path.write_text('[layouts.compact]\ncolumns = ["Nonsense"]\n')

    try:
        load_tui_config(path)
    except TuiConfigError as exc:
        assert "Nonsense" in str(exc)
    else:
        raise AssertionError("expected TuiConfigError")


def test_load_tui_config_rejects_unknown_preset_name(tmp_path: Path) -> None:
    path = tmp_path / "tui.toml"
    path.write_text('[layouts.roomy]\ncolumns = ["Stars"]\n')

    try:
        load_tui_config(path)
    except TuiConfigError:
        pass
    else:
        raise AssertionError("expected TuiConfigError")


def test_load_tui_config_invalid_toml_raises(tmp_path: Path) -> None:
    path = tmp_path / "tui.toml"
    path.write_text("this is not [ valid toml")

    try:
        load_tui_config(path)
    except TuiConfigError:
        pass
    else:
        raise AssertionError("expected TuiConfigError")


def test_load_tui_config_rejects_unknown_category_colour_role(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tui.toml"
    path.write_text('[category_colours]\nAI = "magenta"\n')

    try:
        load_tui_config(path)
    except TuiConfigError as exc:
        assert "category_colours" in str(exc)
    else:
        raise AssertionError("expected TuiConfigError")


def test_load_tui_config_invalid_schema_raises(tmp_path: Path) -> None:
    path = tmp_path / "tui.toml"
    path.write_text('header_height = "not an int"')

    try:
        load_tui_config(path)
    except TuiConfigError:
        pass
    else:
        raise AssertionError("expected TuiConfigError")


# -- load_tui_state / save_tui_state ------------------------------------


def test_load_tui_state_missing_file_is_every_default(tmp_path: Path) -> None:
    state = load_tui_state(tmp_path / "tui-state.toml")

    assert state == TuiState()
    assert state.view_mode == "list"
    assert state.sort_key is None
    assert state.filter is None
    # `None` means "follow the active layout preset" (ADR 0008); the
    # field only holds a bool once the user toggles the pane.
    assert state.detail_pane_visible is None
    assert state.layout is None


def test_load_tui_state_corrupt_file_falls_back_to_defaults(tmp_path: Path) -> None:
    """Unlike `tui.toml`, a corrupt machine-written state file must not
    block the TUI from launching."""
    path = tmp_path / "tui-state.toml"
    path.write_text("not [ valid")

    state = load_tui_state(path)

    assert state == TuiState()


def test_save_then_load_tui_state_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "tui-state.toml"
    state = TuiState(
        view_mode="folder",
        sort_key="newest",
        filter="unclassified",
        detail_pane_visible=False,
        layout="balanced",
    )

    save_tui_state(path, state)
    loaded = load_tui_state(path)

    assert loaded == state


def test_save_tui_state_omits_none_fields_and_still_round_trips(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tui-state.toml"
    state = TuiState()  # sort_key and filter both None

    save_tui_state(path, state)
    loaded = load_tui_state(path)

    assert loaded == state
    assert "sort_key" not in path.read_text()
    assert "filter" not in path.read_text()


def test_save_tui_state_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "tui-state.toml"

    save_tui_state(path, TuiState())

    assert path.exists()


# -- TuiApp integration --------------------------------------------------


async def test_tui_app_with_no_config_file_uses_defaults(
    tmp_path: Path, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=tmp_path / "config" / "tui.toml",
        state_path=tmp_path / "state" / "tui-state.toml",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        action_text = str(app.query_one("#action-controls", Static).render())

    # The default tag key remains visible in the bottom status bar.
    assert "[t] Tag" in action_text


async def test_tui_app_applies_keybinding_override(
    tmp_path: Path, make_star: StarFactory
) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('[keybindings]\ntag_selected = "shift+t"\n')

    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=config_path,
        state_path=tmp_path / "state" / "tui-state.toml",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        # The old "t" key must no longer trigger the picker.
        await pilot.press("t")
        await pilot.pause()
        old_key_screen_count = len(app.screen_stack)
        # The new "shift+t" key must trigger it instead.
        await pilot.press("shift+t")
        await pilot.pause()
        new_key_screen_count = len(app.screen_stack)

    assert old_key_screen_count == 1  # no picker opened
    assert new_key_screen_count == 2  # picker opened


async def test_keybinding_override_preserves_inherited_app_bindings(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Regression test (code review finding): applying even one
    `[keybindings]` override must not clobber the App-level bindings
    `TuiApp` never declares itself -- `ctrl+q` (force quit), `ctrl+c`,
    and the command palette's `ctrl+p` -- which live in the merged
    binding map Textual's own `DOMNode.__init__` builds from the whole
    class hierarchy, not just `TuiApp.BINDINGS`.
    """
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('[keybindings]\ntag_selected = "shift+t"\n')

    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=config_path,
        state_path=tmp_path / "state" / "tui-state.toml",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        bound_keys = set(app._bindings.key_to_bindings)

    assert {"ctrl+q", "ctrl+c", "ctrl+p"} <= bound_keys


async def test_tui_app_applies_row_and_header_height(
    tmp_path: Path, make_star: StarFactory
) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("header_height = 3\n\n[layouts.compact]\nrow_height = 2\n")

    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=config_path,
        state_path=tmp_path / "state" / "tui-state.toml",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)

    assert table.header_height == 3
    assert table.get_row_height(RowKey("pradyumnac/ghstars")) == 2


async def test_tui_app_never_writes_tui_config(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """ADR 0002: `config/tui.toml` is stow-managed; ghstars only ever
    reads it in this ticket. A launch + quit cycle must leave it
    untouched -- missing stays missing."""
    config_path = tmp_path / "config" / "tui.toml"
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=config_path,
        state_path=tmp_path / "state" / "tui-state.toml",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.action_quit()

    assert not config_path.exists()


async def test_tui_app_persists_last_layout_over_config_default(
    tmp_path: Path, make_star: StarFactory
) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('layout = "compact"\n')
    state_path = tmp_path / "state" / "tui-state.toml"
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app1 = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=config_path,
        state_path=state_path,
    )
    async with app1.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app1.action_cycle_layout()
        await pilot.pause()
        await app1.action_quit()

    assert load_tui_state(state_path).layout == "balanced"

    app2 = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=config_path,
        state_path=state_path,
    )
    async with app2.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        columns = [str(column.label) for column in _table(app2).columns.values()]

    assert {"License", "Owner", "Starred at"} <= set(columns)


async def test_tui_app_restores_view_mode_across_relaunch(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Ticket 21 stub: there is no View Mode switcher yet (ticket 25
    builds it), so this exercises the persistence plumbing directly --
    a future switcher only needs to mutate `app._state.view_mode`, this
    round trip already works end to end."""
    state_path = tmp_path / "state" / "tui-state.toml"
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app1 = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=tmp_path / "config" / "tui.toml",
        state_path=state_path,
    )
    async with app1.run_test() as pilot:
        await pilot.pause()
        app1._state.view_mode = "folder"
        await app1.action_quit()

    app2 = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=tmp_path / "config" / "tui.toml",
        state_path=state_path,
    )
    async with app2.run_test() as pilot:
        await pilot.pause()
        restored_view_mode = app2._state.view_mode

    assert restored_view_mode == "folder"


async def test_tui_app_restores_sort_key_across_relaunch(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Ticket 27 (partial): the active sort key persists into
    tui-state.toml on quit and is restored on the next launch, same
    round trip as view_mode above."""
    state_path = tmp_path / "state" / "tui-state.toml"
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app1 = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=tmp_path / "config" / "tui.toml",
        state_path=state_path,
    )
    async with app1.run_test() as pilot:
        await pilot.pause()
        assert app1._sort_mode == "starred_desc"  # default before any toggle
        await pilot.press("s")
        assert app1._sort_mode == "name"
        await app1.action_quit()

    app2 = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=tmp_path / "config" / "tui.toml",
        state_path=state_path,
    )
    async with app2.run_test() as pilot:
        await pilot.pause()
        restored_sort_mode = app2._sort_mode

    assert restored_sort_mode == "name"


async def test_tui_app_ignores_unrecognized_saved_sort_key(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """An older/newer ghstars version's sort key set differing from
    this build's `_SORT_MODES` must fall back to the default, not
    crash `_sorted_stars()` with an unrecognized mode."""
    from ghstars.tui.config import TuiState, save_tui_state

    state_path = tmp_path / "state" / "tui-state.toml"
    save_tui_state(state_path, TuiState(sort_key="some_future_key"))
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app = TuiApp(
        client=FakeGitHubClient(),
        store=store,
        config_path=tmp_path / "config" / "tui.toml",
        state_path=state_path,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._sort_mode == "starred_desc"
