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
fetched once on mount and shown in the title row. Press `r` to refresh
it. This warns the user before `ghstars sync` reaches the API limit
(docs/explanation/known-limitations.md: a full sync is not
incremental and costs real API points every time).

This module never syncs automatically. The TUI starts a sync only when
the user presses its explicit sync key; otherwise it reads and tags against
the last local snapshot.

Config (`ghstars.tui.config`): `config/tui.toml` sets the keybindings,
the header height, the presentation fields (date format, toast timeout,
ASCII markers, clock, default Filter), and the layout presets. Each
preset holds its own ordered column list and sizing. The file is read in
`__init__`, before the first paint. The config editor writes it only when
Esc validates a changed form (ADR 0002). `state/tui-state.toml` remembers
the active preset, sort key, Filter, and detail-pane override, read at
launch and written on quit (`action_quit`).

Terminal width never drops a column and never hides the detail pane (ADR
0008). The table scrolls horizontally instead.
"""

import hashlib
import json
import webbrowser
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import tomlkit
from filelock import Timeout
from pydantic import ValidationError
from rich.style import Style
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.markup import escape
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import Button, Checkbox, DataTable, Input, Label, Select, Static
from tomlkit.exceptions import TOMLKitError

from ghstars.core.github_client import GitHubClient
from ghstars.core.models import List, RateLimitStatus, Star
from ghstars.core.state_store import StateStore
from ghstars.core.sync import sync
from ghstars.core.tagging import bulk_tag_stars
from ghstars.core.unstar import unstar_star
from ghstars.github import GitHubApiError
from ghstars.tui.config import (
    CATEGORY_COLOURS_DARK,
    CATEGORY_COLOURS_LIGHT,
    DEFAULT_DATE_FORMAT,
    DEFAULT_KEYBINDINGS,
    CategoryColourName,
    ColumnName,
    LayoutPreset,
    TuiConfig,
    TuiState,
    load_tui_config,
    load_tui_state,
    save_tui_state,
)


def _default_binding(action: str, description: str, *, show: bool = True) -> Binding:
    """Bind an action to its `DEFAULT_KEYBINDINGS` key."""
    return Binding(DEFAULT_KEYBINDINGS[action], action, description, show=show)


_LOCK = "\U0001f512"
_GLOBE = "\U0001f310"
_ASCII_LOCK = "P"
_ASCII_GLOBE = "G"


@dataclass(frozen=True)
class _StatusGlyphs:
    """The title and status markers, in one Unicode set and one ASCII
    set. `ascii_only` picks the set at launch, so a terminal without a
    usable font still reads every state as distinct text."""

    title: str
    api: str
    sync: str
    done: str
    failed: str


_UNICODE_GLYPHS = _StatusGlyphs(
    title="\u2726", api="\u25cc", sync="\u21bb", done="\u2713", failed="\u2715"
)
_ASCII_GLYPHS = _StatusGlyphs(title="*", api="?", sync="o", done="ok", failed="x")
_CATEGORY_COLOUR_NAMES: tuple[CategoryColourName, ...] = tuple(CATEGORY_COLOURS_LIGHT)


def _category_colour(
    category: str | None, overrides: Mapping[str, CategoryColourName]
) -> CategoryColourName | None:
    """Return the named colour for a Category, or `None` for no Category.

    A digest of the name picks the default, so the same Category keeps
    its colour across launches and across TUI surfaces. Two names can
    collide; the Category text is the primary cue, so a collision only
    costs a shade (ADR 0008).
    """
    if not category:
        return None
    if category in overrides:
        return overrides[category]
    index = hashlib.sha256(category.encode()).digest()[0] % len(_CATEGORY_COLOUR_NAMES)
    return _CATEGORY_COLOUR_NAMES[index]


def _rich_colour(value: str) -> str:
    """Convert a Textual RGBA hex value to the RGB form Rich accepts."""
    return value[:7] if value.startswith("#") and len(value) == 9 else value


@dataclass(frozen=True)
class CategoryPalette:
    """The hex values a Category cue draws with under one active theme.

    Built per render pass, not cached: the user can switch theme mid
    session, and a light theme and a dark theme need different hexes for
    the same named colour (`tui/config.py`).
    """

    muted: str
    hexes: Mapping[CategoryColourName, str]

    @classmethod
    def of[ReturnType](cls, app: App[ReturnType]) -> CategoryPalette:
        variables = app.get_css_variables()
        return cls(
            # `$text-muted` is a Textual expression (`auto 60%`), not a Rich
            # colour. Use the active theme's muted foreground instead.
            muted=_rich_colour(variables["foreground-muted"]),
            hexes=(
                CATEGORY_COLOURS_DARK
                if app.current_theme.dark
                else CATEGORY_COLOURS_LIGHT
            ),
        )

    def style_for(
        self, category: str | None, overrides: Mapping[str, CategoryColourName]
    ) -> str:
        colour = _category_colour(category, overrides)
        return self.muted if colour is None else self.hexes[colour]


def _styled_category(
    category: str | None,
    palette: CategoryPalette,
    overrides: Mapping[str, CategoryColourName],
) -> Text:
    """Render Category text in its named colour."""
    return Text(category or "-", style=palette.style_for(category, overrides))


def _styled_list(
    lst: List, palette: CategoryPalette, overrides: Mapping[str, CategoryColourName]
) -> Text:
    """Render a full List name while keeping its Category as the colour cue."""
    text = Text()
    if lst.intent and lst.category:
        text.append(f"{lst.intent}: ")
        text.append_text(_styled_category(lst.category, palette, overrides))
    else:
        text.append(lst.name, style=palette.muted)
    return text


def _membership_chip(
    lst: List,
    palette: CategoryPalette,
    overrides: Mapping[str, CategoryColourName],
    *,
    ascii_only: bool = False,
) -> Text:
    """Render one text-first Intent and Category membership cue."""
    lock, globe = (_ASCII_LOCK, _ASCII_GLOBE) if ascii_only else (_LOCK, _GLOBE)
    text = Text(f"[{lock if lst.is_private else globe} ")
    if lst.intent and lst.category:
        text.append(f"{lst.intent} · ")
        text.append_text(_styled_category(lst.category, palette, overrides))
    else:
        text.append(lst.name, style=palette.muted)
    text.append("]")
    text.stylize(Style(meta={"@click": f"app.filter_membership({lst.id!r})"}))
    return text


def _membership_chips(
    lists: list[List],
    palette: CategoryPalette,
    overrides: Mapping[str, CategoryColourName],
    *,
    ascii_only: bool = False,
) -> Text:
    """Render several membership cues without hiding their text labels."""
    if not lists:
        return Text("-")
    text = Text()
    for index, lst in enumerate(lists):
        if index:
            text.append(" ")
        text.append_text(
            _membership_chip(lst, palette, overrides, ascii_only=ascii_only)
        )
    return text


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


def _visibility_label(is_private: bool, *, ascii_only: bool = False) -> str:
    lock, globe = (_ASCII_LOCK, _ASCII_GLOBE) if ascii_only else (_LOCK, _GLOBE)
    return f"{lock} Private" if is_private else f"{globe} Public"


def _format_date(value: datetime | None, date_format: str = DEFAULT_DATE_FORMAT) -> str:
    return "-" if value is None else value.strftime(date_format)


def _yes_no(value: bool) -> str:
    """Word markers, not glyphs: a boolean column reads the same under
    `ascii_only`."""
    return "yes" if value else "no"


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

    def __init__(
        self,
        *,
        category_colours: Mapping[str, CategoryColourName] | None = None,
        date_format: str = DEFAULT_DATE_FORMAT,
        ascii_only: bool = False,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._category_colours = category_colours or {}
        self._date_format = date_format
        self._ascii_only = ascii_only

    def _date(self, value: datetime | None) -> str:
        return _format_date(value, self._date_format)

    def _visibility(self, is_private: bool) -> str:
        return _visibility_label(is_private, ascii_only=self._ascii_only)

    def show_star(self, star: Star, lists: dict[str, List]) -> None:
        member_lists = [lists[lid] for lid in star.list_ids if lid in lists]
        memberships = (
            ", ".join(
                f"{lst.name} ({self._visibility(lst.is_private)})"
                for lst in member_lists
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
            f"License: {star.license or '-'}",
            f"Stars: {star.stargazer_count}",
            f"Fork: {star.fork}    Follow: {star.follow}",
            f"Archived: {star.archived}"
            + (f" (at {self._date(star.archived_at)})" if star.archived_at else ""),
            (
                f"Starred: {self._date(star.starred_at)}    "
                f"First seen: {self._date(star.first_seen)}    "
                f"Last checked: {self._date(star.last_checked)}"
            ),
            f"Lists: {memberships}",
            f"Pending list edit: {pending}",
        ]
        body = Text.from_markup("\n".join(lines[:-2]))
        body.append("\nLists: ")
        if member_lists:
            for index, lst in enumerate(member_lists):
                if index:
                    body.append(", ")
                body.append_text(
                    _styled_list(
                        lst,
                        CategoryPalette.of(self.app),
                        self._category_colours,
                    )
                )
                body.append(f" ({self._visibility(lst.is_private)})")
        else:
            body.append("none")
        body.append(f"\nPending list edit: {pending}")
        self.update(body)

    def show_empty(self) -> None:
        self.update("No star selected.")


class ListPickerScreen(ModalScreen[TagChoice | None]):
    """Pick an existing List, or type a new one, to tag into.

    Every existing List's row shows its public/private status
    explicitly, so picking a List that looks similar to another never
    silently lands a Star in the wrong visibility.
    """

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        lists: list[List],
        *,
        target_count: int,
        category_colours: Mapping[str, CategoryColourName] | None = None,
        ascii_only: bool = False,
    ) -> None:
        super().__init__()
        self._lists = sorted(lists, key=lambda lst: lst.name)
        self._target_count = target_count
        self._category_colours = category_colours or {}
        self._ascii_only = ascii_only

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
        palette = CategoryPalette.of(self.app)
        for lst in self._lists:
            table.add_row(
                _styled_list(lst, palette, self._category_colours),
                lst.intent or "-",
                _styled_category(lst.category, palette, self._category_colours),
                _visibility_label(lst.is_private, ascii_only=self._ascii_only),
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


class FilterMenuScreen(ModalScreen[str | None]):
    """Choose a filter type or clear the active filter."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "category", "Category"),
        Binding("i", "intent", "Intent"),
        Binding("l", "list", "List"),
        Binding("g", "language", "Language"),
        Binding("v", "license", "License"),
        Binding("r", "recency", "Recency"),
        Binding("o", "owner", "Owner"),
        Binding("k", "forks", "Forks"),
        Binding("w", "followed", "Followed"),
        Binding("u", "unclassified", "Unclassified"),
        Binding("x", "clear", "Clear"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-body"):
            yield Static("Filter")
            yield DataTable(id="filter-menu-table", cursor_type="row")
            yield Static(
                "Shortcuts: c Category  i Intent  l List  g Language  v License  r Recency  o Owner  k Forks  w Followed  u Unclassified  x Clear"
            )
            yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        table = self.query_one("#filter-menu-table", DataTable)
        table.add_column("Action")
        for key, label in (
            ("category", "Category"),
            ("intent", "Intent"),
            ("list", "List"),
            ("language", "Language"),
            ("license", "License"),
            ("recency", "Recency"),
            ("owner", "Owner"),
            ("forks", "Forks only"),
            ("followed", "Followed owners only"),
            ("unclassified", "Unclassified (no List)"),
            ("clear", "Clear active filter"),
        ):
            table.add_row(label, key=key)
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.dismiss(event.row_key.value)

    def action_category(self) -> None:
        self.dismiss("category")

    def action_intent(self) -> None:
        self.dismiss("intent")

    def action_list(self) -> None:
        self.dismiss("list")

    def action_language(self) -> None:
        self.dismiss("language")

    def action_license(self) -> None:
        self.dismiss("license")

    def action_recency(self) -> None:
        self.dismiss("recency")

    def action_owner(self) -> None:
        self.dismiss("owner")

    def action_forks(self) -> None:
        self.dismiss("forks")

    def action_followed(self) -> None:
        self.dismiss("followed")

    def action_unclassified(self) -> None:
        self.dismiss("unclassified")

    def action_clear(self) -> None:
        self.dismiss("clear")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# The clear-filter option's label, per filter kind. The TUI holds one
# filter key at a time, so every one of these clears the whole filter
# and shows every Star. The wording names the screen the user is on.
_CLEAR_FILTER_LABELS: dict[str, str] = {
    "category": "All categories",
    "intent": "All intents",
    "list": "All lists",
    "language": "All languages",
    "license": "All licenses",
    "owner": "All owners",
    "recency": "Any star date",
}


class FilterScreen(ModalScreen[str | None]):
    """Choose one value for a filter."""

    # The clear-filter option's value. `_set_filter` reads any falsy
    # value as "clear the filter".
    _CLEAR_VALUE: ClassVar[str] = ""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("d", "recent_day", "", show=False),
        Binding("w", "recent_week", "", show=False),
        Binding("m", "recent_month", "", show=False),
        Binding("3", "recent_three_months", "", show=False),
        Binding("y", "recent_year", "", show=False),
        Binding("o", "recent_older", "", show=False),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        options: Sequence[tuple[str, str | Text]],
        *,
        clear_label: str = "All stars",
    ) -> None:
        super().__init__()
        self._title = title
        self._options = list(options)
        self._option_values = {value for value, _ in options}
        self._clear_label = clear_label
        self._selected_value: str | None = None

    @staticmethod
    def _match_rank(label: str, query: str) -> tuple[bool, bool, str]:
        """Rank one option against the query, best first.

        Order: an exact match, then a prefix match, then any other
        substring match. Ties break alphabetically. Each flag is `False`
        when the option matches better, because `sort()` puts `False`
        before `True`.

        An empty query gives every option the same two flags, so the
        alphabetical tiebreak decides the whole order.
        """
        lowered = label.lower()
        return (lowered != query, not lowered.startswith(query), lowered)

    def _visible_options(self) -> list[tuple[str, str | Text]]:
        """Filter and rank every option the screen can show.

        The clear option is always in the set, so an empty query shows
        it without a search. It always ranks last, so Enter on a fresh
        screen applies a real option and never clears the filter by
        accident.
        """
        query = self.query_one("#filter-query", Input).value.strip().lower()
        options = list(self._options)
        if query:
            options = [
                (value, label)
                for value, label in options
                if query in str(label).lower()
            ]
        options.sort(key=lambda option: self._match_rank(str(option[1]), query))
        if not query or query in self._clear_label.lower():
            options.append((self._CLEAR_VALUE, self._clear_label))
        return options

    def _refresh_options(self) -> None:
        table = self.query_one("#filter-table", DataTable)
        table.clear()
        options = self._visible_options()
        self._selected_value = options[0][0] if options else None
        for value, label in options:
            table.add_row(label, key=value)
        if options:
            table.move_cursor(row=0)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "filter-query":
            return
        if self._title.startswith("Filter by Recency"):
            shortcuts = {
                "d": self.action_recent_day,
                "w": self.action_recent_week,
                "m": self.action_recent_month,
                "3": self.action_recent_three_months,
                "y": self.action_recent_year,
                "o": self.action_recent_older,
            }
            action = shortcuts.get(event.value.lower())
            if action is not None:
                action()
                return
        self._refresh_options()

    def on_key(self, event: events.Key) -> None:
        if not self._title.startswith("Filter by Recency"):
            return
        shortcuts = {
            "d": self.action_recent_day,
            "w": self.action_recent_week,
            "m": self.action_recent_month,
            "3": self.action_recent_three_months,
            "y": self.action_recent_year,
            "o": self.action_recent_older,
        }
        action = shortcuts.get(event.key)
        if action is not None:
            event.stop()
            action()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "filter-query":
            return
        if self._selected_value is not None:
            self.dismiss(self._selected_value)

    def _select_shortcut(self, value: str) -> None:
        if value in self._option_values:
            self.dismiss(value)

    def action_recent_day(self) -> None:
        self._select_shortcut("recent:1d")

    def action_recent_week(self) -> None:
        self._select_shortcut("recent:1w")

    def action_recent_month(self) -> None:
        self._select_shortcut("recent:1m")

    def action_recent_three_months(self) -> None:
        self._select_shortcut("recent:3m")

    def action_recent_year(self) -> None:
        self._select_shortcut("recent:1y")

    def action_recent_older(self) -> None:
        self._select_shortcut("recent:older_1y")

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-body"):
            yield Static(self._title)
            yield Input(placeholder="Search filters...", id="filter-query")
            yield DataTable(id="filter-table", cursor_type="row")
            yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        table = self.query_one("#filter-table", DataTable)
        table.add_column("Filter")
        self._refresh_options()
        self.query_one("#filter-query", Input).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.dismiss(event.row_key.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ListsOverviewScreen(ModalScreen[None]):
    """Read-only view of every locally synced List, visibility shown."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]

    def __init__(
        self,
        lists: list[List],
        *,
        category_colours: Mapping[str, CategoryColourName] | None = None,
        ascii_only: bool = False,
    ) -> None:
        super().__init__()
        self._lists = sorted(lists, key=lambda lst: lst.name)
        self._category_colours = category_colours or {}
        self._ascii_only = ascii_only

    def compose(self) -> ComposeResult:
        with Vertical(id="lists-overview"):
            yield Static(f"{len(self._lists)} List(s) -- Esc to close")
            yield DataTable(id="overview-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#overview-table", DataTable)
        table.add_columns("List", "Intent", "Category", "Visibility", "Items")
        palette = CategoryPalette.of(self.app)
        for lst in self._lists:
            table.add_row(
                _styled_list(lst, palette, self._category_colours),
                lst.intent or "-",
                _styled_category(lst.category, palette, self._category_colours),
                _visibility_label(lst.is_private, ascii_only=self._ascii_only),
                str(len(lst.items)),
                key=lst.id,
            )

    def action_close(self) -> None:
        self.dismiss(None)


class ConfigInput(Input):
    """An editor input where `x` discards the form."""

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "x":
            event.stop()
            event.prevent_default()
            self.screen.dismiss(False)
            return
        await super()._on_key(event)


class ConfigSelect(Select[object]):
    """An editor selector where `x` discards the form."""

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "x":
            event.stop()
            event.prevent_default()
            self.screen.dismiss(False)
            return
        await super()._on_key(event)


class ConfigEditorScreen(ModalScreen[bool]):
    """Edit `tui.toml` from a new disk snapshot.

    The running app keeps its launch snapshot until restart.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "save", "Save", priority=True),
        Binding("x", "cancel", "Discard", priority=True),
    ]

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.config = load_tui_config(path)
        self._original = self.config.model_dump(mode="json")

    def compose(self) -> ComposeResult:
        with Vertical(id="config-editor"):
            with Horizontal(id="config-header"):
                yield Static(f"Config: {self.path}", id="config-title")
                yield Static("Esc Save  •  x Discard", id="config-help")
            with VerticalScroll(id="config-scroll"):
                with Vertical(classes="config-section"):
                    yield Static("General", classes="config-section-title")
                    for key, label, value in (
                        ("header_height", "Header height", self.config.header_height),
                        ("date_format", "Date format", self.config.date_format),
                        ("toast_timeout", "Toast timeout", self.config.toast_timeout),
                        (
                            "default_filter",
                            "Default Filter",
                            self.config.default_filter or "",
                        ),
                    ):
                        with Horizontal(classes="config-row"):
                            yield Label(label, classes="config-label")
                            yield ConfigInput(
                                str(value),
                                id=f"config-{key}",
                                classes="config-input",
                            )
                    with Horizontal(classes="config-row"):
                        yield Label("Initial Layout", classes="config-label")
                        yield ConfigSelect(
                            [("Compact", "compact"), ("Balanced", "balanced")],
                            value=self.config.layout,
                            id="config-layout",
                            classes="config-boolean-input",
                        )
                    for key, label, value in (
                        ("show_clock", "Show clock", self.config.show_clock),
                        ("ascii_only", "ASCII only", self.config.ascii_only),
                    ):
                        with Horizontal(classes="config-row"):
                            yield Label(label, classes="config-label")
                            yield ConfigSelect(
                                [("Yes", True), ("No", False)],
                                value=value,
                                id=f"config-{key}",
                                classes="config-boolean-input",
                            )

                with Vertical(classes="config-section"):
                    yield Static("Category colours", classes="config-section-title")
                    for category, colour in self.config.category_colours.items():
                        with Horizontal(classes="config-row"):
                            yield Label("Category", classes="config-label")
                            yield ConfigInput(
                                category,
                                id=f"category-name-{category}",
                                classes="config-category-input",
                            )
                            yield ConfigSelect(
                                [(name, name) for name in _CATEGORY_COLOUR_NAMES],
                                value=colour,
                                id=f"category-colour-{category}",
                                classes="config-key-input",
                            )
                    with Horizontal(classes="config-row"):
                        yield Label("Add category", classes="config-label")
                        yield ConfigInput(
                            "",
                            placeholder="Category name",
                            id="category-name-new",
                            classes="config-category-input",
                        )
                        yield ConfigSelect(
                            [(name, name) for name in _CATEGORY_COLOUR_NAMES],
                            id="category-colour-new",
                            classes="config-key-input",
                        )

                for name, preset in self.config.layouts.items():
                    with Vertical(classes="config-section"):
                        yield Static(
                            f"{name.title()} Layout", classes="config-section-title"
                        )
                        with Horizontal(classes="config-row"):
                            yield Label("Columns", classes="config-label")
                            yield ConfigInput(
                                ", ".join(preset.columns),
                                id=f"layout-columns-{name}",
                                classes="config-columns-input",
                            )
                        with Horizontal(classes="config-row"):
                            yield Label("Detail pane visible", classes="config-label")
                            yield ConfigSelect(
                                [("Yes", True), ("No", False)],
                                value=preset.detail_pane_visible,
                                id=f"layout-visible-{name}",
                                classes="config-boolean-input",
                            )
                        with Horizontal(classes="config-row"):
                            yield Label("Row height", classes="config-label")
                            yield ConfigInput(
                                str(preset.row_height),
                                id=f"layout-row-height-{name}",
                                classes="config-key-input",
                            )
                        with Horizontal(classes="config-row"):
                            yield Label("Detail pane height", classes="config-label")
                            yield ConfigInput(
                                str(preset.detail_pane_height),
                                id=f"layout-pane-height-{name}",
                                classes="config-key-input",
                            )

                with Vertical(classes="config-section"):
                    yield Static("Keybindings", classes="config-section-title")
                    for action in DEFAULT_KEYBINDINGS:
                        with Horizontal(classes="config-row"):
                            yield Label(
                                action.replace("_", " ").title(),
                                classes="config-label",
                            )
                            yield ConfigInput(
                                self.config.keybindings.get(
                                    action, DEFAULT_KEYBINDINGS[action]
                                ),
                                id=f"binding-{action}",
                                classes="config-key-input",
                            )

    def on_mount(self) -> None:
        self.query_one("#config-header_height", Input).focus()

    def _values(self) -> dict[str, object]:
        def text(key: str) -> str:
            return self.query_one(f"#config-{key}", Input).value

        def integer(key: str) -> int:
            try:
                return int(text(key))
            except ValueError as exc:
                raise ValueError(f"{key} must be an integer") from exc

        values: dict[str, object] = {
            "header_height": integer("header_height"),
            "date_format": text("date_format"),
            "toast_timeout": integer("toast_timeout"),
            "default_filter": text("default_filter") or None,
            "show_clock": self.query_one("#config-show_clock", Select).value,
            "ascii_only": self.query_one("#config-ascii_only", Select).value,
            "layout": self.query_one("#config-layout", Select).value,
            "keybindings": {},
            "category_colours": {},
            "layouts": {},
        }
        values["keybindings"] = {
            action: self.query_one(f"#binding-{action}", Input).value
            for action in DEFAULT_KEYBINDINGS
            if self.query_one(f"#binding-{action}", Input).value
            != DEFAULT_KEYBINDINGS[action]
        }
        colours: dict[str, str] = {}
        for category in self.config.category_colours:
            name = self.query_one(f"#category-name-{category}", Input).value.strip()
            colour = str(
                self.query_one(f"#category-colour-{category}", Select).value or ""
            ).strip()
            if name and colour:
                colours[name] = colour
        new_name = self.query_one("#category-name-new", Input).value.strip()
        new_colour = str(
            self.query_one("#category-colour-new", Select).value or ""
        ).strip()
        if new_name and new_colour:
            colours[new_name] = new_colour
        values["category_colours"] = colours
        values["layouts"] = {
            name: {
                "columns": [
                    column.strip()
                    for column in self.query_one(
                        f"#layout-columns-{name}", Input
                    ).value.split(",")
                    if column.strip()
                ],
                "detail_pane_visible": self.query_one(
                    f"#layout-visible-{name}", Select
                ).value,
                "row_height": self._integer_input(
                    f"#layout-row-height-{name}", "row height"
                ),
                "detail_pane_height": self._integer_input(
                    f"#layout-pane-height-{name}", "detail pane height"
                ),
            }
            for name in self.config.layouts
        }
        return values

    def _integer_input(self, selector: str, label: str) -> int:
        try:
            return int(self.query_one(selector, Input).value)
        except ValueError as exc:
            raise ValueError(f"{label} must be an integer") from exc

    def action_save(self) -> None:
        try:
            values = self._values()
            validated = TuiConfig.model_validate(values)
        except (ValueError, TypeError, TOMLKitError) as exc:
            self.notify(f"Invalid configuration: {exc}", severity="error")
            return
        document = (
            tomlkit.parse(self.path.read_text())
            if self.path.exists()
            else tomlkit.document()
        )
        changed = validated.model_dump(mode="json") != self._original
        if not changed:
            self.dismiss(False)
            return
        current = validated.model_dump(mode="json")
        original = self._original
        for key in (
            "header_height",
            "date_format",
            "toast_timeout",
            "ascii_only",
            "default_filter",
            "show_clock",
            "layout",
        ):
            if current[key] != original[key]:
                document[key] = current[key]
        if current["keybindings"] != original["keybindings"]:
            document["keybindings"] = current["keybindings"]
        if current["category_colours"] != original["category_colours"]:
            document["category_colours"] = current["category_colours"]
        if current["layouts"] != original["layouts"]:
            document["layouts"] = current["layouts"]
        for key, value in current.items():
            if key not in document and value == original[key] and key != "layout":
                document.add(tomlkit.comment(f"{key} = {value!r} (default)"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(tomlkit.dumps(document))
        self.app.notify("Config saved. Restart ghstars to apply changes.")
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class TuiApp(App[None]):
    """Interactive triage: tag, bulk-tag, and retag Stars (ticket 09)."""

    CSS = """
    #picker-body, #lists-overview, #confirm-body, #filter-body {
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
    ConfigEditorScreen {
        align: center middle;
    }
    #config-editor {
        width: 80%;
        height: 85%;
        max-width: 100;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #config-scroll {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
        scrollbar-size-vertical: 1;
    }
    #config-header {
        height: 2;
        padding: 0 1;
    }
    #config-title {
        width: 1fr;
        text-style: bold;
    }
    #config-help {
        width: auto;
        color: $text-muted;
        text-align: right;
    }
    .config-section {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
        padding: 1 2;
        background: $panel;
    }
    .config-section-title {
        text-style: bold;
        color: $text-accent;
        margin-bottom: 1;
    }
    .config-row {
        width: 1fr;
        height: 3;
        align: left middle;
    }
    .config-label {
        width: 24;
        padding-right: 2;
    }
    .config-input {
        width: 1fr;
        max-width: 54;
    }
    .config-key-input, .config-boolean-input {
        width: 20;
    }
    .config-category-input {
        width: 1fr;
        max-width: 32;
    }
    .config-columns-input {
        width: 1fr;
    }
    #title-row, #discovery-row, #bottom-status-row {
        height: 1;
        margin: 0 1;
        padding: 0 1;
        background: $panel;
    }
    #title-label, #action-controls {
        width: 1fr;
    }
    #action-controls {
        text-align: right;
    }
    #discovery-row {
        align: right middle;
    }
    #bottom-status-row {
        align: left middle;
    }
    #clock {
        width: auto;
        text-align: right;
        padding-left: 2;
    }
    #system-status, #collection-status {
        width: auto;
        text-align: right;
    }
    #discovery-controls {
        width: auto;
        text-align: left;
    }
    #system-status.-low {
        color: $text-error;
    }
    #search-input {
        display: none;
    }
    #stars-table {
        height: 1fr;
        margin: 1;
        border: round $primary;
        overflow-x: auto;
    }
    DetailPane {
        height: 14;
        padding: 1 2;
        background: $panel;
        border: round $primary;
    }
    """

    _FOOTER_SEP = " •"

    # Keys come from `DEFAULT_KEYBINDINGS`, the canonical map `tui.toml`
    # validation checks a user override against.
    BINDINGS: ClassVar[list[BindingType]] = [
        _default_binding("quit", f"Quit{_FOOTER_SEP}"),
        _default_binding("tag_selected", f"Tag / Retag{_FOOTER_SEP}"),
        _default_binding("toggle_detail_pane", f"Detail{_FOOTER_SEP}"),
        _default_binding("toggle_select", f"Select{_FOOTER_SEP}"),
        _default_binding("select_all", f"Select all{_FOOTER_SEP}"),
        _default_binding("clear_selection", f"Clear selection{_FOOTER_SEP}"),
        _default_binding("show_lists", f"Lists{_FOOTER_SEP}"),
        _default_binding("open_filter", "Filter", show=False),
        _default_binding("clear_discovery", "Clear", show=False),
        _default_binding("cycle_layout", f"Layout{_FOOTER_SEP}"),
        _default_binding("open_in_browser", f"Open{_FOOTER_SEP}"),
        _default_binding("unstar_selected", f"Unstar{_FOOTER_SEP}"),
        # Keep the sort label synchronized with the active mode.
        _default_binding("cycle_sort", "Sort (Date)", show=False),
        _default_binding("open_search", "Search", show=False),
        # Hide this contextual binding from persistent key hints.
        _default_binding("close_search", "Close search", show=False),
        _default_binding("refresh_rate_limit", "Refresh rate limit"),
        _default_binding("sync", f"Sync{_FOOTER_SEP}"),
        Binding("g", "edit_config", f"Config{_FOOTER_SEP}"),
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
        self._filter_open = False
        self._unstar_confirm_open = False
        self._api_low = False

        # Use explicit paths when provided; otherwise use the standard local paths.
        self._config_path = config_path or (
            store.base_dir.parent / "config" / "tui.toml"
        )
        self._state_path = state_path or (store.base_dir / "tui-state.toml")
        self._config: TuiConfig = load_tui_config(self._config_path)
        self._state: TuiState = load_tui_state(self._state_path)
        self._glyphs = _ASCII_GLYPHS if self._config.ascii_only else _UNICODE_GLYPHS
        self._clock_timer: Timer | None = None
        self._api_status = f"{self._glyphs.api} checking"
        self._sync_status = f"{self._glyphs.sync} idle"
        # No filter in state means no filter the user picked, so config's
        # default applies -- on a first launch and after a clear alike.
        self._filter_key = self._state.filter or self._config.default_filter
        self._layout = self._state.layout or self._config.layout

        # Restore a recognized sort mode; default to newest starred date.
        saved_sort_key = self._state.sort_key
        self._sort_mode = (
            saved_sort_key if saved_sort_key in self._SORT_MODES else "starred_desc"
        )

        # Apply overrides before the first render.
        self._apply_keybinding_overrides(self._config.keybindings)

    @property
    def _preset(self) -> LayoutPreset:
        """Sizing and columns for the active layout. State picks the
        preset; config defines it (ADR 0008)."""
        return self._config.layouts[
            "balanced" if self._layout == "balanced" else "compact"
        ]

    def _detail_pane_wanted(self) -> bool:
        """The preset's value, unless this session overrode it. `z`
        clears the override, so a layout switch restores the preset."""
        if self._state.detail_pane_visible is None:
            return self._preset.detail_pane_visible
        return self._state.detail_pane_visible

    def compose(self) -> ComposeResult:
        with Horizontal(id="title-row"):
            yield Static(f"{self._glyphs.title} ghstars", id="title-label")
            yield Static(id="system-status")
            if self._config.show_clock:
                yield Static(id="clock")
        with Horizontal(id="discovery-row"):
            yield Static(id="collection-status")
        yield Input(placeholder="Search name/description...", id="search-input")
        yield DataTable(
            id="stars-table",
            cursor_type="row",
            header_height=self._config.header_height,
        )
        yield DetailPane(
            category_colours=self._config.category_colours,
            date_format=self._config.date_format,
            ascii_only=self._config.ascii_only,
            id="detail-pane",
        )
        with Horizontal(id="bottom-status-row"):
            yield Static(id="discovery-controls")
            yield Static(id="action-controls")

    def on_mount(self) -> None:
        self.title = "ghstars"
        table = self.query_one("#stars-table", DataTable)
        self._configure_table_columns(table)
        pane = self.query_one("#detail-pane", DetailPane)
        pane.styles.height = self._preset.detail_pane_height
        pane.display = self._detail_pane_wanted()
        self._update_sort_binding_description()
        self._refresh_clock()
        self._refresh_system_status()
        self._reload_local_state()
        self._refresh_table()
        self._fetch_rate_limit()
        # Focus the table instead of the hidden search input on startup.
        table.focus()

    def get_system_commands(self, screen: Screen[object]) -> Iterator[SystemCommand]:
        """Add the two config commands to Ctrl+P's command palette."""
        commands = tuple(super().get_system_commands(screen))
        return iter(
            commands
            + (
                SystemCommand("Edit config", "Edit tui.toml", self.action_edit_config),
                SystemCommand(
                    "Show config path",
                    "Print the tui.toml path",
                    self.action_show_config_path,
                ),
            )
        )

    def action_edit_config(self) -> None:
        self.push_screen(ConfigEditorScreen(self._config_path))

    def action_show_config_path(self) -> None:
        print(self._config_path)
        self.notify(str(self._config_path))

    async def action_quit(self) -> None:
        """Persist `state/tui-state.toml` before exiting (spec story 71).

        Overrides `App.action_quit` -- bound to the existing `q` entry
        in `BINDINGS` above, unchanged -- rather than hooking
        `on_unmount`, so the write happens deterministically before
        Textual starts tearing the app down, not racing it.
        """
        if isinstance(self.screen, ConfigEditorScreen):
            return
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

        Every override reaching this method already passed
        `TuiConfig`'s keybinding validation at load time -- a known
        action, a parseable key, no reserved key, and no collision in
        the merged map -- so it never has to reject one here (ticket 21
        made an unknown action a silent no-op instead).
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

    def _configure_table_columns(self, table: DataTable[object]) -> None:
        """Build the column set from the active preset's ordered
        `columns` list. Sel and Star always lead (ADR 0008). Terminal
        width never drops a column -- the table scrolls instead."""
        table.clear(columns=True)
        table.add_columns(("Sel", "sel"), "Star")
        for name in self._preset.columns:
            table.add_column(name)

    def _refresh_clock(self) -> None:
        """Paint the clock and keep it ticking. A first cut: ticket 24
        rebuilds the header this widget sits in."""
        if not self._config.show_clock:
            return
        # `astimezone()` on an aware UTC value is the local wall clock,
        # which is what a header clock must show.
        local = datetime.now(UTC).astimezone()
        self.query_one("#clock", Static).update(local.strftime("%H:%M"))
        if self._clock_timer is None:
            self._clock_timer = self.set_interval(1, self._refresh_clock)

    def _refresh_system_status(self) -> None:
        """Render API and sync state in the title row."""
        status = self.query_one("#system-status", Static)
        status.update(f"[{self._api_status}]  [{self._sync_status}]")
        status.set_class(self._api_low, "-low")

    def _refresh_discovery_status(self, visible_count: int) -> None:
        """Render discovery controls and collection counts."""
        variables = self.get_css_variables()
        accent = _rich_colour(variables["text-accent"])
        active = _rich_colour(variables["text-primary"])
        action_controls = Text()
        for key, label in (
            ("t", "Tag"),
            ("d", "Detail"),
            ("spc", "Select"),
            ("l", "Lists"),
            ("o", "Open"),
            ("u", "Unstar"),
            ("y", "Sync"),
            ("g", "Config"),
            ("q", "Quit"),
        ):
            if action_controls:
                action_controls.append("  ")
            action_controls.append(f"[{key}]", style=accent)
            action_controls.append(f" {label}")
        self.query_one("#action-controls", Static).update(action_controls)

        controls = Text()
        for key, label in (("/", "Search"), ("f", "Filter"), ("s", "Sort")):
            if controls:
                controls.append("  ")
            controls.append(f"[{key}]", style=accent)
            value = label
            if label == "Search" and self._search_query.strip():
                value = f"Search: {self._search_query.strip()}"
            elif label == "Filter":
                value = f"Filter: {self._filter_label() if self._filter_key else 'All'}"
            elif label == "Sort":
                value = f"Sort: {self._SORT_LABELS[self._sort_mode]}"
            controls.append(f" {value}", style=active if ":" in value else None)
        controls.append("  ")
        controls.append("[x]", style=accent)
        controls.append(" Clear")
        self.query_one("#discovery-controls", Static).update(controls)

        unclassified = sum(not star.list_ids for star in self._stars)
        pending = sum(bool(star.pending_list_ids) for star in self._stars)
        counts = Text(
            f"[Stars: {visible_count}/{len(self._stars)}]  "
            f"[Lists: {len(self._lists)}]  "
        )
        start = len(counts)
        counts.append(f"[Unclassified: {unclassified}]")
        counts.stylize(
            Style(
                color=accent,
                meta={"@click": "app.filter_unclassified"},
            ),
            start,
        )
        counts.append(f"  [Pending: {pending}]")
        self.query_one("#collection-status", Static).update(counts)

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
                timeout=self._config.toast_timeout,
            )
            return False
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            self.notify(
                f"could not load local state — {exc}",
                severity="error",
                timeout=self._config.toast_timeout,
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
        """Apply the active List filter and search query to sorted Stars."""
        stars = self._sorted_stars()
        filter_key = self._filter_key or ""
        if filter_key == "unclassified":
            stars = [star for star in stars if not star.list_ids]
        elif filter_key.startswith("category:"):
            category = filter_key.removeprefix("category:")
            ids = {lst.id for lst in self._lists if lst.category == category}
            stars = [star for star in stars if set(star.list_ids) & ids]
        elif filter_key.startswith("intent:"):
            intent = filter_key.removeprefix("intent:")
            ids = {lst.id for lst in self._lists if lst.intent == intent}
            stars = [star for star in stars if set(star.list_ids) & ids]
        elif filter_key.startswith("list:"):
            list_id = filter_key.removeprefix("list:")
            stars = [star for star in stars if list_id in star.list_ids]
        elif filter_key.startswith("language:"):
            language = filter_key.removeprefix("language:")
            stars = [star for star in stars if star.language == language]
        elif filter_key.startswith("license:"):
            license_name = filter_key.removeprefix("license:")
            stars = [star for star in stars if star.license == license_name]
        elif filter_key.startswith("owner:"):
            owner = filter_key.removeprefix("owner:")
            stars = [star for star in stars if star.full_name.split("/", 1)[0] == owner]
        elif filter_key == "forks":
            stars = [star for star in stars if star.fork]
        elif filter_key == "followed":
            stars = [star for star in stars if star.follow]
        elif filter_key.startswith("recent:"):
            cutoff = datetime.now(UTC) - {
                "1d": timedelta(days=1),
                "1w": timedelta(weeks=1),
                "1m": timedelta(days=30),
                "3m": timedelta(days=90),
                "1y": timedelta(days=365),
            }.get(filter_key.removeprefix("recent:"), timedelta(0))
            if filter_key == "recent:older_1y":
                cutoff = datetime.now(UTC) - timedelta(days=365)
                stars = [star for star in stars if star.starred_at < cutoff]
            else:
                stars = [star for star in stars if star.starred_at >= cutoff]

        query = self._search_query.strip().lower()
        if query:
            stars = [
                star
                for star in stars
                if query in star.full_name.lower()
                or (star.description is not None and query in star.description.lower())
            ]
        return stars

    def _date(self, value: datetime | None) -> str:
        return _format_date(value, self._config.date_format)

    def _column_cell(
        self, name: ColumnName, star: Star, member_lists: list[List]
    ) -> object:
        """Render one configured column's cell for a Star."""
        if name == "Owner":
            return star.full_name.split("/", 1)[0]
        if name == "Language":
            return star.language or "-"
        if name == "License":
            return star.license or "-"
        if name == "Stars":
            return _format_count(star.stargazer_count)
        if name == "Starred at":
            return self._date(star.starred_at)
        if name == "First seen":
            return self._date(star.first_seen)
        if name == "Last checked":
            return self._date(star.last_checked)
        if name == "Archived at":
            return self._date(star.archived_at)
        if name == "Fork":
            return _yes_no(star.fork)
        if name == "Follow":
            return _yes_no(star.follow)
        if name == "Archived":
            return _yes_no(star.archived)
        # "Membership" is the only name left in `ColumnName`.
        return _membership_chips(
            member_lists,
            CategoryPalette.of(self),
            self._config.category_colours,
            ascii_only=self._config.ascii_only,
        )

    def _refresh_table(self) -> None:
        table = self.query_one("#stars-table", DataTable)
        table.clear()
        visible_stars = self._visible_stars()
        self._refresh_discovery_status(len(visible_stars))
        by_id = self._lists_by_id()
        for star in visible_stars:
            mark = "[x]" if star.full_name in self._selected else "[ ]"
            member_lists = [by_id[lid] for lid in star.list_ids if lid in by_id]
            row: list[object] = [mark, star.full_name]
            row.extend(
                self._column_cell(name, star, member_lists)
                for name in self._preset.columns
            )
            table.add_row(
                *row,
                height=self._preset.row_height,
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
        self._state.detail_pane_visible = pane.display
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
        self.push_screen(
            ListsOverviewScreen(
                self._lists,
                category_colours=self._config.category_colours,
                ascii_only=self._config.ascii_only,
            )
        )

    def action_refresh_rate_limit(self) -> None:
        self._fetch_rate_limit()

    def action_sync(self) -> None:
        if getattr(self, "_sync_in_progress", False):
            self.notify("Sync already in progress.", severity="warning")
            return
        self._sync_in_progress = True
        self._sync_status = f"{self._glyphs.sync} starting"
        self._refresh_system_status()
        self._run_sync()

    @work(thread=True)
    def _run_sync(self) -> None:
        def on_stage(stage: str) -> None:
            self.call_from_thread(self._show_sync_stage, stage)

        try:
            result = sync(self._client, self._store, on_stage=on_stage)
        except Exception as exc:  # noqa: BLE001 -- worker must report all failures
            self.call_from_thread(self._show_sync_error, str(exc))
            return
        self.call_from_thread(
            self._show_sync_done, result.star_count, result.list_count
        )

    def _show_sync_stage(self, stage: str) -> None:
        self._sync_status = f"{self._glyphs.sync} {stage}"
        self._refresh_system_status()

    def _show_sync_done(self, star_count: int, list_count: int) -> None:
        self._sync_in_progress = False
        self._reload_local_state()
        self._refresh_table()
        self._sync_status = (
            f"{self._glyphs.done} complete · {star_count} Stars · {list_count} Lists"
        )
        self._refresh_system_status()
        self.notify(f"Synced {star_count} star(s), {list_count} list(s).")

    def _show_sync_error(self, detail: str) -> None:
        self._sync_in_progress = False
        self._sync_status = f"{self._glyphs.failed} failed: {detail}"
        self._refresh_system_status()
        self.notify(
            f"Sync failed: {detail}",
            severity="error",
            timeout=self._config.toast_timeout,
        )

    # Cycle through the supported sort modes with "s".
    _SORT_MODES: ClassVar[list[str]] = [
        "starred_desc",
        "name",
        "stargazer_desc",
        "language",
        "list_count_desc",
        "list_name",
    ]
    # Short form for the bottom status bar's active sort value.
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
        """Keep the sort binding description in step with the status bar.

        The binding description remains useful in the command palette even
        though the persistent hint now lives in the custom bottom bar.
        """
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

    def action_cycle_layout(self) -> None:
        """Toggle compact and balanced columns and save the active density."""
        self._layout = "balanced" if self._layout == "compact" else "compact"
        self._state.layout = self._layout
        # A layout switch drops the session override (ADR 0008).
        self._state.detail_pane_visible = None
        pane = self.query_one("#detail-pane", DetailPane)
        pane.styles.height = self._preset.detail_pane_height
        pane.display = self._detail_pane_wanted()
        table = self.query_one("#stars-table", DataTable)
        self._configure_table_columns(table)
        self._refresh_table()
        self.notify(f"Layout: {self._layout}.")

    def action_cycle_sort(self) -> None:
        index = self._SORT_MODES.index(self._sort_mode)
        self._sort_mode = self._SORT_MODES[(index + 1) % len(self._SORT_MODES)]
        # Persist the mode when the app exits.
        self._state.sort_key = self._sort_mode
        self._refresh_table()
        self._update_sort_binding_description()
        self.notify(f"Sorted by {self._SORT_NOTIFY_LABELS[self._sort_mode]}.")

    # -- filters --------------------------------------------------------------

    def action_filter_membership(self, list_id: str) -> None:
        """Apply the exact Intent-and-Category List selected in a chip."""
        self._set_filter(f"list:{list_id}")

    def action_filter_unclassified(self) -> None:
        self._set_filter("unclassified")

    def action_clear_discovery(self) -> None:
        """Clear search and Filter state without changing the active sort."""
        self._filter_key = None
        self._state.filter = None
        self._search_query = ""
        search_input = self.query_one("#search-input", Input)
        search_input.value = ""
        search_input.display = False
        self._refresh_table()
        self.query_one("#stars-table", DataTable).focus()

    def _set_filter(self, value: str | None) -> None:
        self._filter_key = value or None
        self._state.filter = self._filter_key
        self._refresh_table()
        self.notify(
            "Filter cleared." if not value else f"Filtered by {self._filter_label()}."
        )

    def _filter_label(self) -> str:
        key = self._filter_key or ""
        if key == "unclassified":
            return "Unclassified (no List)"
        if ":" in key:
            kind, value = key.split(":", 1)
            if kind == "list":
                return next((lst.name for lst in self._lists if lst.id == value), value)
            return f"{kind.title()}: {value}"
        return key

    @work
    async def _open_filter(self) -> None:
        if self._filter_open:
            return
        self._filter_open = True
        try:
            kind = await self.push_screen_wait(FilterMenuScreen())
            options: list[tuple[str, str | Text]]
            if kind in {"clear", "unclassified"}:
                self._set_filter(None if kind == "clear" else kind)
                return
            if kind == "category":
                values = sorted({lst.category for lst in self._lists if lst.category})
                palette = CategoryPalette.of(self)
                options = [
                    (
                        f"category:{value}",
                        _styled_category(value, palette, self._config.category_colours),
                    )
                    for value in values
                ]
                title = "Filter by Category"
            elif kind == "intent":
                values = sorted({lst.intent for lst in self._lists if lst.intent})
                options = [(f"intent:{value}", value) for value in values]
                title = "Filter by Intent"
            elif kind == "list":
                palette = CategoryPalette.of(self)
                options = [
                    (
                        f"list:{lst.id}",
                        _styled_list(lst, palette, self._config.category_colours),
                    )
                    for lst in sorted(self._lists, key=lambda item: item.name)
                ]
                title = "Filter by List"
            elif kind == "language":
                values = sorted(
                    {star.language for star in self._stars if star.language}
                )
                options = [(f"language:{value}", value) for value in values]
                title = "Filter by Language"
            elif kind == "license":
                values = sorted({star.license for star in self._stars if star.license})
                options = [(f"license:{value}", value) for value in values]
                title = "Filter by License"
            elif kind == "owner":
                values = sorted(
                    {star.full_name.split("/", 1)[0] for star in self._stars}
                )
                options = [(f"owner:{value}", value) for value in values]
                title = "Filter by Owner"
            elif kind == "forks":
                options = [("forks", "Forks only")]
                title = "Filter Forks"
            elif kind == "followed":
                options = [("followed", "Followed owners only")]
                title = "Filter Followed"
            elif kind == "recency":
                options = [
                    ("recent:1d", "Starred in the last 1 day"),
                    ("recent:1w", "Starred in the last 1 week"),
                    ("recent:1m", "Starred in the last 1 month"),
                    ("recent:3m", "Starred in the last 3 months"),
                    ("recent:1y", "Starred in the last 1 year"),
                    ("recent:older_1y", "Starred more than 1 year ago"),
                ]
                title = "Filter by Recency (d/w/m/3/y/o)"
            else:
                return
            value = await self.push_screen_wait(
                FilterScreen(
                    title,
                    options,
                    clear_label=_CLEAR_FILTER_LABELS.get(kind, "All stars"),
                )
            )
            if value is not None:
                self._set_filter(value)
        finally:
            self._filter_open = False

    def action_open_filter(self) -> None:
        self._open_filter()

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
        self.notify(
            f"{full_name}: unstar failed: {exc}",
            severity="error",
            timeout=self._config.toast_timeout,
        )

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
                ListPickerScreen(
                    self._lists,
                    target_count=len(targets),
                    category_colours=self._config.category_colours,
                    ascii_only=self._config.ascii_only,
                )
            )
        finally:
            self._picker_open = False
        if choice is not None:
            self._apply_tag(targets, choice)

    @work(thread=True)
    def _apply_tag(self, targets: list[str], choice: TagChoice) -> None:
        """Runs off the UI thread: `bulk_tag_stars()` touches the
        file-locked StateStore and, for a real client, shells out to
        `gh`. The batching, per-star failure isolation, and node-ID /
        `lists`-snapshot reuse this used to do inline now live in
        `ghstars.core.tagging.bulk_tag_stars()` (ticket 31, Scope C) so
        the CLI can reuse the same orchestration -- see that function's
        docstring for the full reasoning. This method's only job is to
        call it and translate its per-repository outcomes into this
        screen's notification.
        """
        outcomes = bulk_tag_stars(
            self._client,
            self._store,
            targets,
            choice.list_name,
            is_private=choice.is_private,
        )
        tagged = 0
        removed_total = 0
        errors: list[str] = []
        for outcome in outcomes:
            if outcome.result is not None:
                tagged += 1
                removed_total += len(outcome.result.removed_list_ids)
            else:
                errors.append(f"{outcome.full_name}: {outcome.error}")
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
            self.notify(error, severity="error", timeout=self._config.toast_timeout)

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
        marker = "LOW " if not status.ok else ""
        self._api_status = (
            f"{self._glyphs.api} {marker}{status.remaining}/{status.limit}"
        )
        self._api_low = not status.ok
        self._refresh_system_status()

    def _show_rate_limit_error(self, detail: str) -> None:
        self._api_status = f"{self._glyphs.api} error"
        self._api_low = True
        self._refresh_system_status()
        self.notify(f"Rate limit check failed: {escape(detail)}", severity="error")
