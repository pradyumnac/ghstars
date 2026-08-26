"""Textual TUI for interactive tagging, bulk-tagging, and retagging.

A thin wrapper over `ghstars.core`: every mutation goes through
`ghstars.core.tagging.tag_star`, the same function `ghstars tag` uses.
Retagging a Star between Categories or Intents needs no separate code
path here -- `tag_star()` already strips a sibling Explore/Current/
Retired List in the same Category when you tag into a new one (spec
story 16), so "tag" and "retag" are the same call from this UI's point
of view: pick a target List, apply it.

Public/private (spec: never mistake a private List for a public one):
every place a List's name appears -- the picker, the read-only Lists
overview, and each Star row's membership summary -- also renders its
visibility explicitly.

Rate limit (spec story 49): `GitHubClient.check_rate_limit()` is
fetched once on mount and shown in a bar under the header, refreshable
with `r`, so the user can see they're approaching a sync-blocking
limit before `ghstars sync` fails outright
(docs/explanation/known-limitations.md: a full sync is not
incremental and costs real API points every time).

This module never calls `ghstars.core.sync`. Syncing stays a
deliberate `ghstars sync` on the command line; this TUI only reads and
tags against whatever was last synced.

Config (ticket 21, `ghstars.tui.config`): `config/tui.toml` overrides
keybindings, header/row sizing, and the colour palette, applied in
`__init__` before the first paint; this module never writes it (ADR
0002). `state/tui-state.toml` remembers the last View Mode, sort key,
and active Filter, read at launch and written on quit
(`action_quit`).
"""

import json
import webbrowser
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from filelock import Timeout
from pydantic import ValidationError
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, DataTable, Footer, Header, Input, Static

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import List, RateLimitStatus, Star
from ghstars.core.state_store import StateStore
from ghstars.core.tagging import (
    StarArchivedError,
    StarListMembershipDriftError,
    StarNotFoundError,
    TagPushError,
    tag_star,
)
from ghstars.core.unstar import unstar_star
from ghstars.github import GitHubApiError
from ghstars.tui.config import (
    TuiColours,
    TuiConfig,
    TuiState,
    load_tui_config,
    load_tui_state,
    save_tui_state,
)

_LOCK = "\U0001f512"
_GLOBE = "\U0001f310"


@dataclass(frozen=True)
class TagChoice:
    """What the List picker returned: a target List name and its visibility.

    `is_private` only matters when `list_name` doesn't match an
    existing List -- `tag_star()` uses it solely when it has to create
    a new List. For a name that already exists, the existing List's
    own visibility wins; this field is ignored.
    """

    list_name: str
    is_private: bool


def _visibility_label(is_private: bool) -> str:
    return f"{_LOCK} Private" if is_private else f"{_GLOBE} Public"


def _format_date(value: datetime | None) -> str:
    return "-" if value is None else value.strftime("%d-%b-%Y")


def _format_count(value: int) -> str:
    """Compact star-count display for the table's narrow "Stars" column
    (e.g. 12345 -> "12.3K", 2_000_000 -> "2M"). The detail pane still
    shows the exact figure -- this is a glanceability shorthand, not
    the only place the real number appears."""
    for threshold, suffix in ((1_000_000, "M"), (1_000, "K")):
        if abs(value) >= threshold:
            scaled = value / threshold
            text = f"{scaled:.1f}".removesuffix(".0")
            return f"{text}{suffix}"
    return str(value)


class DetailPane(Static):
    """Shows every field the last `ghstars sync` stored for the Star
    under the cursor (spec story 59), including `description` and
    `html_url` -- neither of which appears anywhere else in this TUI.

    Reads only from the `Star` object handed to it; never touches
    `GitHubClient`, so it can never block the initial paint.
    """

    def show_star(self, star: Star, lists: dict[str, List]) -> None:
        memberships = (
            ", ".join(
                f"{lists[lid].name} ({_visibility_label(lists[lid].is_private)})"
                for lid in star.list_ids
                if lid in lists
            )
            or "none"
        )
        pending = (
            "none pending"
            if star.pending_list_ids is None
            else ", ".join(star.pending_list_ids) or "none pending"
        )
        lines = [
            f"[b]{star.full_name}[/b]",
            star.html_url,
            "",
            star.description or "(no description)",
            "",
            f"Language: {star.language or '-'}",
            f"Stars: {star.stargazer_count}",
            f"Fork: {star.fork}    Follow: {star.follow}",
            f"Archived: {star.archived}"
            + (f" (at {_format_date(star.archived_at)})" if star.archived_at else ""),
            (
                f"Starred: {_format_date(star.starred_at)}    "
                f"First seen: {_format_date(star.first_seen)}    "
                f"Last checked: {_format_date(star.last_checked)}"
            ),
            f"Lists: {memberships}",
            f"Pending list edit: {pending}",
        ]
        self.update("\n".join(lines))

    def show_empty(self) -> None:
        self.update("No star selected.")


class RateLimitBar(Static):
    """Shows the remaining GitHub API rate limit (spec story 49).

    Constructed with a "checking" placeholder rather than empty content:
    a real `check_rate_limit()` call takes ~0.7s, and an empty `Static`
    paints as a blank strip for that whole window -- indistinguishable
    from the bar being broken.
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("API rate limit: checking...", id=id)

    def show_status(self, status: RateLimitStatus) -> None:
        marker = "ok" if status.ok else "LOW"
        self.update(
            f"API rate limit: {status.remaining}/{status.limit} remaining ({marker})"
        )
        self.set_class(not status.ok, "-low")

    def show_unknown(self, detail: str) -> None:
        # Escape arbitrary error text before rendering it as markup.
        self.update(f"API rate limit: unknown ({escape(detail)})")
        self.set_class(True, "-low")


class ListPickerScreen(ModalScreen[TagChoice | None]):
    """Pick an existing List, or type a new one, to tag into.

    Every existing List's row shows its public/private status
    explicitly, so picking a List that looks similar to another never
    silently lands a Star in the wrong visibility.
    """

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, lists: list[List], *, target_count: int) -> None:
        super().__init__()
        self._lists = sorted(lists, key=lambda lst: lst.name)
        self._target_count = target_count

    def compose(self) -> ComposeResult:
        noun = "star" if self._target_count == 1 else "stars"
        with Vertical(id="picker-body"):
            yield Static(f"Tag {self._target_count} {noun} into a List")
            yield DataTable(id="picker-table", cursor_type="row")
            yield Input(
                placeholder="Or type a new List name, e.g. 'Explore: Foo'",
                id="new-list-input",
            )
            yield Checkbox("Private (new List only)", id="private-checkbox")
            with Horizontal(id="picker-buttons"):
                yield Button("Tag", id="confirm", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        table = self.query_one("#picker-table", DataTable)
        table.add_columns("List", "Intent", "Category", "Visibility")
        for lst in self._lists:
            table.add_row(
                lst.name,
                lst.intent or "-",
                lst.category or "-",
                _visibility_label(lst.is_private),
                key=lst.id,
            )
        self.query_one("#new-list-input", Input).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key.value
        lst = next((item for item in self._lists if item.id == row_key), None)
        if lst is not None:
            self.dismiss(TagChoice(list_name=lst.name, is_private=lst.is_private))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._confirm_new_name()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self._confirm_new_name()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _confirm_new_name(self) -> None:
        name = self.query_one("#new-list-input", Input).value.strip()
        if not name:
            self.app.bell()
            return
        is_private = self.query_one("#private-checkbox", Checkbox).value
        self.dismiss(TagChoice(list_name=name, is_private=is_private))


class ConfirmUnstarScreen(ModalScreen[bool]):
    """A real, irreversible GitHub mutation (spec stories 67-68) must
    never fire from one keypress -- this gate is the only way in."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, full_name: str) -> None:
        super().__init__()
        self._full_name = full_name

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-body"):
            yield Static(
                f"Unstar [b]{escape(self._full_name)}[/b] on GitHub?\n"
                "This removes the star from your GitHub account."
            )
            with Horizontal(id="picker-buttons"):
                yield Button("Unstar", id="confirm", variant="error")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)


class ListsOverviewScreen(ModalScreen[None]):
    """Read-only view of every locally synced List, visibility shown."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]

    def __init__(self, lists: list[List]) -> None:
        super().__init__()
        self._lists = sorted(lists, key=lambda lst: lst.name)

    def compose(self) -> ComposeResult:
        with Vertical(id="lists-overview"):
            yield Static(f"{len(self._lists)} List(s) -- Esc to close")
            yield DataTable(id="overview-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#overview-table", DataTable)
        table.add_columns("List", "Intent", "Category", "Visibility", "Items")
        for lst in self._lists:
            table.add_row(
                lst.name,
                lst.intent or "-",
                lst.category or "-",
                _visibility_label(lst.is_private),
                str(len(lst.items)),
                key=lst.id,
            )

    def action_close(self) -> None:
        self.dismiss(None)


class TuiApp(App[None]):
    """Interactive triage: tag, bulk-tag, and retag Stars (ticket 09)."""

    CSS = """
    #picker-body, #lists-overview, #confirm-body {
        width: 80%;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #picker-buttons {
        height: auto;
        align: right middle;
    }
    #picker-buttons Button {
        margin-left: 1;
    }
    RateLimitBar {
        height: 1;
        padding: 0 1;
        background: $panel;
    }
    RateLimitBar.-low {
        background: $error;
        color: $text;
    }
    #search-input {
        display: none;
    }
    #stars-table {
        height: 1fr;
    }
    DetailPane {
        height: 14;
        padding: 1 2;
        background: $panel;
        border: round $primary;
    }
    """

    _FOOTER_SEP = " •"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", f"Quit{_FOOTER_SEP}"),
        Binding("t", "tag_selected", f"Tag / Retag{_FOOTER_SEP}"),
        Binding("d", "toggle_detail_pane", f"Detail{_FOOTER_SEP}"),
        Binding("space", "toggle_select", f"Select{_FOOTER_SEP}"),
        Binding("a", "select_all", f"Select all{_FOOTER_SEP}"),
        Binding("c", "clear_selection", f"Clear selection{_FOOTER_SEP}"),
        Binding("l", "show_lists", f"Lists{_FOOTER_SEP}"),
        Binding("o", "open_in_browser", f"Open{_FOOTER_SEP}"),
        Binding("u", "unstar_selected", f"Unstar{_FOOTER_SEP}"),
        # Keep the sort label synchronized with the active mode.
        Binding("s", "cycle_sort", f"Sort (Date){_FOOTER_SEP}"),
        Binding("slash", "open_search", f"Search{_FOOTER_SEP}"),
        # Hide this contextual binding from the Footer.
        Binding("escape", "close_search", "Close search", show=False),
        Binding("r", "refresh_rate_limit", "Refresh rate limit"),
    ]

    def __init__(
        self,
        client: GitHubClient,
        store: StateStore,
        *,
        config_path: Path | None = None,
        state_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._client = client
        self._store = store
        self._stars: list[Star] = []
        self._lists: list[List] = []
        self._selected: set[str] = set()
        self._search_query = ""
        self._picker_open = False
        self._unstar_confirm_open = False

        # Use explicit paths when provided; otherwise use the standard local paths.
        self._config_path = config_path or (
            store.base_dir.parent / "config" / "tui.toml"
        )
        self._state_path = state_path or (store.base_dir / "tui-state.toml")
        self._config: TuiConfig = load_tui_config(self._config_path)
        self._state: TuiState = load_tui_state(self._state_path)

        # Restore a recognized sort mode; default to newest starred date.
        saved_sort_key = self._state.sort_key
        self._sort_mode = (
            saved_sort_key if saved_sort_key in self._SORT_MODES else "starred_desc"
        )

        # Apply overrides before the first render.
        self._apply_keybinding_overrides(self._config.keybindings)
        self._apply_colour_overrides(self._config.colours)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RateLimitBar(id="rate-limit-bar")
        yield Input(placeholder="Search name/description...", id="search-input")
        yield DataTable(
            id="stars-table",
            cursor_type="row",
            header_height=self._config.header_height,
        )
        yield DetailPane(id="detail-pane")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "ghstars"
        table = self.query_one("#stars-table", DataTable)
        table.add_columns(("Sel", "sel"), "Star", "Language", "Stars", "Lists")
        # The table fills the space when the detail pane is hidden.
        self._update_sort_binding_description()
        self._reload_local_state()
        self._refresh_table()
        self._fetch_rate_limit()
        # Focus the table instead of the hidden search input on startup.
        table.focus()

    async def action_quit(self) -> None:
        """Persist `state/tui-state.toml` before exiting (spec story 71).

        Overrides `App.action_quit` -- bound to the existing `q` entry
        in `BINDINGS` above, unchanged -- rather than hooking
        `on_unmount`, so the write happens deterministically before
        Textual starts tearing the app down, not racing it.
        """
        save_tui_state(self._state_path, self._state)
        await super().action_quit()

    # -- config: keybindings and colour palette -------------------------

    def _apply_keybinding_overrides(self, overrides: dict[str, str]) -> None:
        """Rebind an action's key per `tui.toml`'s `[keybindings]` table
        (e.g. `tag_selected = "shift+t"`). Composes with the static
        `BINDINGS` list declared on this class -- it changes which key
        triggers an existing `action_*`, it never adds a new action --
        rather than replacing Textual's binding mechanism.

        Mutates `self._bindings.key_to_bindings` in place -- the merged
        map `DOMNode.__init__` already built from the full class
        hierarchy, not just `self.BINDINGS` -- moving only the key(s)
        currently bound to an overridden action. Rebuilding
        `self._bindings` from `self.BINDINGS` alone (an earlier version
        of this method did exactly that) silently dropped every
        App-level binding TuiApp itself never declares -- `ctrl+q`
        force-quit, `ctrl+c`, and the command palette's `ctrl+p` among
        them -- the moment a user configured even one override.

        An override naming an action with no matching `action_<name>`
        method, or with no existing key bound to it, is a silent no-op
        -- config plumbing only, no new UI, never a hard error.
        """
        if not overrides:
            return
        key_to_bindings = self._bindings.key_to_bindings
        for action, raw_key in overrides.items():
            normalized_key = next(
                iter(Binding.make_bindings([Binding(raw_key, action, "")]))
            ).key
            for key in list(key_to_bindings):
                moved = [b for b in key_to_bindings[key] if b.action == action]
                if not moved:
                    continue
                remaining = [b for b in key_to_bindings[key] if b.action != action]
                if remaining:
                    key_to_bindings[key] = remaining
                else:
                    del key_to_bindings[key]
                key_to_bindings.setdefault(normalized_key, []).extend(
                    replace(b, key=normalized_key) for b in moved
                )

    def _apply_colour_overrides(self, colours: TuiColours) -> None:
        """Apply `tui.toml`'s `[colours]` table on top of the active
        Textual theme (`textual-dark` by default), via Textual's own
        theme system (`App.register_theme`/`App.theme`) rather than
        hand-rolled CSS variable injection. `colours.text` maps to the
        `$text` CSS variable via `Theme.variables` -- `Theme` itself has
        no `text` field (Textual derives it from `foreground` by
        default), so it is the one field that goes through `variables`
        instead of a constructor keyword.
        """
        overrides = colours.model_dump(exclude_none=True)
        text_override = overrides.pop("text", None)
        if not overrides and text_override is None:
            return
        base = self.get_theme(self.theme)
        assert base is not None, f"active theme {self.theme!r} is not registered"
        variables = dict(base.variables)
        if text_override is not None:
            variables["text"] = text_override
        custom = replace(base, name="ghstars-config", variables=variables, **overrides)
        self.register_theme(custom)
        self.theme = "ghstars-config"

    # -- local state, read from the last `ghstars sync` --------------------

    def _reload_local_state(self) -> bool:
        """Load `self._stars`/`self._lists` from the store, tolerating a
        concurrent `ghstars` process holding the state lock or a
        corrupt/truncated state file. Returns whether the reload
        succeeded.

        Called both on first mount (where `self._stars`/`self._lists`
        already default to `[]`) and after a tag push completes. A
        `Timeout` here must not crash the app either time -- on mount,
        the TUI still opens (empty, with an error notification) rather
        than never launching at all; after a tag push, the last
        successfully loaded state is left in place rather than wiped,
        same as `_fetch_rate_limit`'s own broad-catch precedent. A
        corrupt `stars.json`/`lists.json` is treated the same way `sync()`
        self-heals from it (`core/sync.py`'s `_load_self_healing`) rather
        than crashing the TUI on mount with a raw traceback.
        """
        try:
            stars = [s for s in self._store.load_stars() if not s.archived]
            lists = self._store.load_lists()
        except Timeout:
            self.notify(
                "could not load local state — another ghstars command may "
                "be running. Try again once it finishes.",
                severity="error",
                timeout=8,
            )
            return False
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            self.notify(
                f"could not load local state — {exc}",
                severity="error",
                timeout=8,
            )
            return False
        self._stars = stars
        self._lists = lists
        return True

    def _lists_by_id(self) -> dict[str, List]:
        return {lst.id: lst for lst in self._lists}

    def _sorted_stars(self) -> list[Star]:
        # Sort by newest starred date unless another mode is active.
        if self._sort_mode == "name":
            return sorted(self._stars, key=lambda s: s.full_name)
        if self._sort_mode == "stargazer_desc":
            return sorted(self._stars, key=lambda s: s.stargazer_count, reverse=True)
        if self._sort_mode == "language":
            return sorted(
                self._stars, key=lambda s: (s.language is None, s.language or "")
            )
        if self._sort_mode == "list_count_desc":
            return sorted(self._stars, key=lambda s: len(s.list_ids), reverse=True)
        if self._sort_mode == "list_name":
            # Sort by each Star's first List name; unlisted Stars go last.
            by_id = self._lists_by_id()

            def _first_list_name(star: Star) -> tuple[bool, str]:
                names = sorted(by_id[lid].name for lid in star.list_ids if lid in by_id)
                return (not names, names[0] if names else "")

            return sorted(self._stars, key=_first_list_name)
        return sorted(self._stars, key=lambda s: s.starred_at, reverse=True)

    def _visible_stars(self) -> list[Star]:
        """`_sorted_stars()` narrowed by the search-as-you-type query
        (spec story 56), case-insensitive substring match on name and
        description. No active query returns every sorted Star."""
        stars = self._sorted_stars()
        query = self._search_query.strip().lower()
        if not query:
            return stars
        return [
            star
            for star in stars
            if query in star.full_name.lower()
            or (star.description is not None and query in star.description.lower())
        ]

    def _refresh_table(self) -> None:
        table = self.query_one("#stars-table", DataTable)
        table.clear()
        by_id = self._lists_by_id()
        for star in self._visible_stars():
            mark = "[x]" if star.full_name in self._selected else "[ ]"
            memberships = ", ".join(
                f"{by_id[lid].name} ({_visibility_label(by_id[lid].is_private)})"
                for lid in star.list_ids
                if lid in by_id
            )
            table.add_row(
                mark,
                star.full_name,
                star.language or "-",
                _format_count(star.stargazer_count),
                memberships or "-",
                height=self._config.row_height,
                key=star.full_name,
            )
        # Refresh the detail pane because rebuilding row 0 emits no highlight event.
        self._refresh_detail_pane()

    def _star_by_full_name(self, full_name: str) -> Star | None:
        return next((s for s in self._stars if s.full_name == full_name), None)

    def _refresh_detail_pane(self) -> None:
        pane = self.query_one("#detail-pane", DetailPane)
        full_name = self._current_row_full_name()
        star = self._star_by_full_name(full_name) if full_name else None
        if star is None:
            pane.show_empty()
        else:
            pane.show_star(star, self._lists_by_id())

    def action_toggle_detail_pane(self) -> None:
        pane = self.query_one("#detail-pane", DetailPane)
        pane.display = not pane.display
        if pane.display:
            self._refresh_detail_pane()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Keeps the detail pane in step with the cursor (spec story 59)
        as the user moves it with the keyboard. `_refresh_table()`
        handles the table-rebuild case itself (see the comment there),
        so this only needs to cover genuine cursor movement."""
        if event.data_table.id != "stars-table":
            return
        self._refresh_detail_pane()

    def _current_row_full_name(self) -> str | None:
        table = self.query_one("#stars-table", DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        return row_key.value

    def _targets(self) -> list[str]:
        if self._selected:
            return sorted(self._selected)
        current = self._current_row_full_name()
        return [current] if current else []

    # -- selection actions ---------------------------------------------------

    def action_toggle_select(self) -> None:
        full_name = self._current_row_full_name()
        if full_name is None:
            return
        if full_name in self._selected:
            self._selected.discard(full_name)
        else:
            self._selected.add(full_name)
        # Update the cell in place so selection does not reset the cursor.
        mark = "[x]" if full_name in self._selected else "[ ]"
        self.query_one("#stars-table", DataTable).update_cell(full_name, "sel", mark)

    def action_select_all(self) -> None:
        self._selected = {s.full_name for s in self._stars}
        self._refresh_table()

    def action_clear_selection(self) -> None:
        self._selected.clear()
        self._refresh_table()

    def action_show_lists(self) -> None:
        self.push_screen(ListsOverviewScreen(self._lists))

    def action_refresh_rate_limit(self) -> None:
        self._fetch_rate_limit()

    # Cycle through the supported sort modes with "s".
    _SORT_MODES: ClassVar[list[str]] = [
        "starred_desc",
        "name",
        "stargazer_desc",
        "language",
        "list_count_desc",
        "list_name",
    ]
    # Short form for the Footer's "Sort (...)" label.
    _SORT_LABELS: ClassVar[dict[str, str]] = {
        "starred_desc": "Date",
        "name": "Name",
        "stargazer_desc": "Stars",
        "language": "Lang",
        "list_count_desc": "Lists#",
        "list_name": "List A-Z",
    }
    # Longer form for the one-off toast on each toggle.
    _SORT_NOTIFY_LABELS: ClassVar[dict[str, str]] = {
        "starred_desc": "star date (newest first)",
        "name": "name",
        "stargazer_desc": "star count (highest first)",
        "language": "language",
        "list_count_desc": "List count (highest first)",
        "list_name": "List name (A to Z)",
    }

    def _update_sort_binding_description(self) -> None:
        """Keeps the Footer's "Sort (...)" label (`BINDINGS` above) in
        step with `self._sort_mode` -- mutates `self._bindings` the
        same way `_apply_keybinding_overrides()` does, then
        `refresh_bindings()` to repaint the Footer."""
        label = self._SORT_LABELS[self._sort_mode]
        key_to_bindings = self._bindings.key_to_bindings
        bindings = key_to_bindings.get("s")
        if not bindings:
            return
        key_to_bindings["s"] = [
            replace(b, description=f"Sort ({label}){self._FOOTER_SEP}")
            if b.action == "cycle_sort"
            else b
            for b in bindings
        ]
        self.refresh_bindings()

    def action_cycle_sort(self) -> None:
        index = self._SORT_MODES.index(self._sort_mode)
        self._sort_mode = self._SORT_MODES[(index + 1) % len(self._SORT_MODES)]
        # Persist the mode when the app exits.
        self._state.sort_key = self._sort_mode
        self._refresh_table()
        self._update_sort_binding_description()
        self.notify(f"Sorted by {self._SORT_NOTIFY_LABELS[self._sort_mode]}.")

    # -- search ---------------------------------------------------------------

    def action_open_search(self) -> None:
        search_input = self.query_one("#search-input", Input)
        search_input.display = True
        search_input.focus()

    def action_close_search(self) -> None:
        """Escape: clears the query (spec story 56 doesn't call for
        "remember it, just hide it" -- a cleared search on close
        matches how "/" reads as a fresh start each time, not a
        pause/resume toggle) and returns focus to the table. Bound at
        the App level so Escape works from anywhere, but a no-op when
        the search box isn't even open, so it doesn't fight some other
        Escape-driven flow in a future feature."""
        search_input = self.query_one("#search-input", Input)
        if not search_input.display:
            return
        search_input.value = ""
        search_input.display = False
        self._search_query = ""
        self._refresh_table()
        self.query_one("#stars-table", DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search-input":
            return
        self._search_query = event.value
        self._refresh_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter: keep the filter active (unlike Escape), just return
        focus to the table so arrow keys/actions work again without an
        extra Tab."""
        if event.input.id != "search-input":
            return
        self.query_one("#stars-table", DataTable).focus()

    # -- open in browser / unstar ---------------------------------------------

    def action_open_in_browser(self) -> None:
        full_name = self._current_row_full_name()
        star = self._star_by_full_name(full_name) if full_name else None
        if star is None:
            self.notify("No star selected.", severity="warning")
            return
        webbrowser.open(star.html_url)

    def action_unstar_selected(self) -> None:
        """A real, irreversible GitHub mutation (spec stories 67-68) --
        single-Star only (the Star under the cursor), never the bulk
        `_selected` set: unstarring several repos from one confirm
        dialog is a much bigger blast radius than tagging several into
        the same List, and isn't what this action is for.
        """
        if self._unstar_confirm_open:
            return
        full_name = self._current_row_full_name()
        if full_name is None:
            self.notify("No star selected.", severity="warning")
            return
        self._unstar_confirm_open = True
        self._confirm_and_unstar(full_name)

    @work
    async def _confirm_and_unstar(self, full_name: str) -> None:
        try:
            confirmed = await self.push_screen_wait(ConfirmUnstarScreen(full_name))
        finally:
            self._unstar_confirm_open = False
        if confirmed:
            self._run_unstar(full_name)

    @work(thread=True)
    def _run_unstar(self, full_name: str) -> None:
        try:
            result = unstar_star(self._client, self._store, full_name)
        except (GitHubApiError, Timeout) as exc:
            self.call_from_thread(self._on_unstar_error, full_name, exc)
            return
        self.call_from_thread(self._on_unstar_done, result.full_name)

    def _on_unstar_done(self, full_name: str) -> None:
        self._selected.discard(full_name)
        self._reload_local_state()
        self._refresh_table()
        self.notify(f"Unstarred {full_name}.")

    def _on_unstar_error(self, full_name: str, exc: Exception) -> None:
        self.notify(f"{full_name}: unstar failed: {exc}", severity="error", timeout=8)

    # -- tagging / bulk-tagging / retagging ----------------------------------

    def action_tag_selected(self) -> None:
        """Tag whatever's targeted: the highlighted Star, or the whole
        selection if one exists (single-item and bulk share this path).
        Since `tag_star()` auto-strips a sibling same-Category List, this
        is also how a Star gets retagged between Intents/Categories.
        """
        if self._picker_open:
            return
        targets = self._targets()
        if not targets:
            self.notify("No star selected.", severity="warning")
            return
        # Set this before scheduling work so repeated keys cannot open two modals.
        self._picker_open = True
        self._open_picker(targets)

    @work
    async def _open_picker(self, targets: list[str]) -> None:
        try:
            choice = await self.push_screen_wait(
                ListPickerScreen(self._lists, target_count=len(targets))
            )
        finally:
            self._picker_open = False
        if choice is not None:
            self._apply_tag(targets, choice)

    @work(thread=True)
    def _apply_tag(self, targets: list[str], choice: TagChoice) -> None:
        """Runs off the UI thread: `tag_star()` touches the file-locked
        StateStore and, for a real client, shells out to `gh`.

        Catches every exception, not just the documented
        `StarNotFoundError`/`StarArchivedError`/`GitHubApiError`. This
        loop runs in a background thread: anything that escapes it (a
        `filelock.Timeout` from a concurrent `ghstars` process holding
        the store's lock, for instance) never reaches
        `call_from_thread`, so the app would sit there with the
        selection intact and no notification -- indistinguishable from
        a hang. One star's unexpected failure should not sacrifice the
        rest of the batch or the user-visible outcome either way.

        Bulk-tagging N Stars into the same List used to cost N redundant
        `fetch_lists()` calls -- `tag_star()` re-fetched every List from
        GitHub on every call, by design, to check live state before
        creating a List. Fixed in ticket 19 (scope 5): `tag_star()` now
        accepts an optional pre-fetched `lists` snapshot, and returns the
        (possibly List-creation-updated) snapshot it used on
        `TagResult.lists`. This loop seeds `lists` as `None` for the
        first star (identical behavior to before: a real fetch) and
        threads each result's `lists` into the next call, so the whole
        batch shares at most one live `fetch_lists()` round trip instead
        of paying it per star. Trade-off: `tag_star()`'s drift check
        (ticket 16) for star N+1 sees star N's own already-applied
        change correctly, but not a change some other process makes
        directly to star N+1 while star N's push is still in flight --
        see the caveat on `tag_star()`'s own docstring. A single-item
        tag never threads `lists`, so it does not have this gap.

        `tag_star()` also pushes each star to GitHub immediately (ticket
        16), which needs GitHub's node ID per star. For more than one
        target, this resolves every target's node ID in one batched
        `resolve_repository_node_ids()` call up front rather than paying
        `tag_star()`'s internal one-round-trip-per-star resolution N
        times -- see docs/explanation/known-limitations.md. A single
        target skips this (no batching win for one repo). A `full_name`
        missing from the batch result (lookup failed, or the repo was
        renamed/deleted) just falls back to `tag_star()`'s own
        resolution for that one star -- isolated the same way a push
        failure already is below, not a reason to fail the whole batch.
        The membership-update pushes themselves stay sequential, one per
        star, preserving this loop's existing per-star failure isolation
        and the incremental notification below.
        """
        tagged = 0
        removed_total = 0
        errors: list[str] = []
        lists: list[List] | None = None
        node_ids: dict[str, str] = {}
        if len(targets) > 1:
            try:
                node_ids = self._client.resolve_repository_node_ids(targets)
            except Exception:  # noqa: BLE001 -- batching is an optimization.
                node_ids = {}
        for full_name in targets:
            try:
                result = tag_star(
                    self._client,
                    self._store,
                    full_name,
                    choice.list_name,
                    is_private=choice.is_private,
                    lists=lists,
                    node_id=node_ids.get(full_name),
                )
            except (
                StarNotFoundError,
                StarArchivedError,
                StarListMembershipDriftError,
                TagPushError,
                GitHubApiError,
            ) as exc:
                errors.append(f"{full_name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 -- see docstring above
                errors.append(f"{full_name}: unexpected error: {exc}")
                continue
            lists = result.lists
            tagged += 1
            removed_total += len(result.removed_list_ids)
        self.call_from_thread(self._on_tag_done, choice, tagged, removed_total, errors)

    def _on_tag_done(
        self, choice: TagChoice, tagged: int, removed_total: int, errors: list[str]
    ) -> None:
        reloaded = self._reload_local_state()
        self._selected.clear()
        self._refresh_table()
        if tagged:
            message = f"Tagged {tagged} star(s) into {choice.list_name!r}."
            if removed_total:
                message += f" ({removed_total} sibling List membership(s) removed.)"
            if not reloaded:
                # Explain that the table still shows pre-tag state.
                message += " (table may not reflect this yet — reload failed.)"
            self.notify(message)
        for error in errors:
            self.notify(error, severity="error", timeout=8)

    # -- rate limit -----------------------------------------------------------

    @work(thread=True)
    def _fetch_rate_limit(self) -> None:
        try:
            status = self._client.check_rate_limit()
        except Exception as exc:  # noqa: BLE001 -- same reasoning as
            # Report unexpected worker errors so the status bar cannot hang.
            self.call_from_thread(self._show_rate_limit_error, str(exc))
            return
        self.call_from_thread(self._show_rate_limit, status)

    def _show_rate_limit(self, status: RateLimitStatus) -> None:
        self.query_one("#rate-limit-bar", RateLimitBar).show_status(status)

    def _show_rate_limit_error(self, detail: str) -> None:
        self.query_one("#rate-limit-bar", RateLimitBar).show_unknown(detail)
        self.notify(f"Rate limit check failed: {escape(detail)}", severity="error")
