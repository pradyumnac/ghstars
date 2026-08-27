"""Tests for the TUI (ticket 09): single-item tagging, bulk tagging,
retagging, List visibility display, and the rate limit bar.

Uses Textual's own `App.run_test()` pilot -- no real terminal, no
network. Every client is `FakeGitHubClient`; mutations only ever touch
`tmp_path` via a real `StateStore`. `tag_star()`'s own mutating work
runs in a `@work(thread=True)` worker, so tests await
`app.workers.wait_for_complete()` after triggering it.
"""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from conftest import StarFactory
from filelock import Timeout
from rich.style import Style
from rich.text import Text
from textual.widgets import DataTable, Input, Label, Static

from ghstars.core.discovery import query_stars
from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List, RateLimitStatus, Star
from ghstars.core.state_store import StateStore
from ghstars.github.schema import RateLimitResponse
from ghstars.tui.app import (
    ConfigEditorScreen,
    ConfirmUnstarScreen,
    DetailPane,
    FilterScreen,
    ListPickerScreen,
    TuiApp,
    _category_colour,
    _format_date,
    _visibility_label,
)
from ghstars.tui.config import (
    CATEGORY_COLOURS_DARK,
    CATEGORY_COLOURS_LIGHT,
    load_tui_config,
    load_tui_state,
)


def _table(app: TuiApp) -> DataTable[str]:
    return app.query_one("#stars-table", DataTable)


def _detail_text(app: TuiApp) -> str:
    return str(app.query_one("#detail-pane", DetailPane).render())


def test_category_colours_are_stable_named_cues() -> None:
    """The digest picks the same colour for the same Category name every
    time. Two names may land on the same colour; the Category text is
    always there to tell them apart (ADR 0008), so nothing asserts that
    the mapping is one to one."""
    colour = _category_colour("AI", {})

    assert colour == _category_colour("AI", {})
    assert colour in CATEGORY_COLOURS_LIGHT
    assert _category_colour("AI", {"AI": "magenta"}) == "magenta"


def test_category_colour_never_hashes_an_empty_category() -> None:
    assert _category_colour(None, {}) is None
    assert _category_colour("", {}) is None


async def test_category_colour_is_stable_across_app_instances(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Two launches of the same store paint the Category the same way."""
    category_list = List(
        id="L1",
        name="Explore: AI",
        slug="explore-ai",
        intent="Explore",
        category="AI",
    )
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars", list_ids=["L1"])])
    store.save_lists([category_list])

    styles: list[list[str]] = []
    for _ in range(2):
        app = TuiApp(client=FakeGitHubClient(), store=store)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            membership: object = _table(app).get_row_at(0)[4]
            assert isinstance(membership, Text)
            styles.append([str(span.style) for span in membership.spans])

    assert styles[0] == styles[1]


async def test_stars_table_shows_membership_with_visibility(
    tmp_path: Path, make_star: StarFactory
) -> None:
    private_list = List(
        id="L1", name="Current: Tool", slug="current-tool", is_private=True
    )
    star = make_star("example-owner/ghstars", list_ids=["L1"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([private_list])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        row = _table(app).get_row_at(0)

    assert row[1] == "example-owner/ghstars"
    membership = str(row[4])
    assert "Current: Tool" in membership
    assert "🔒" in membership
    assert "pending" not in membership


async def test_category_override_colours_membership_without_hiding_text(
    tmp_path: Path, make_star: StarFactory
) -> None:
    category_list = List(
        id="L1",
        name="Explore: AI",
        slug="explore-ai",
        intent="Explore",
        category="AI",
    )
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("example-owner/ghstars", list_ids=["L1"])])
    store.save_lists([category_list])
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text('[category_colours]\nAI = "magenta"\n')

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        membership: object = _table(app).get_row_at(0)[4]
        theme_colours = (
            CATEGORY_COLOURS_DARK if app.current_theme.dark else CATEGORY_COLOURS_LIGHT
        )
        expected = theme_colours["magenta"]

    assert isinstance(membership, Text)
    assert str(membership) == "[🌐 Explore · AI]"
    assert any(str(span.style) == expected for span in membership.spans)


async def test_category_colour_follows_the_active_theme_polarity(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A light theme takes the light hex table. No single hex clears 3:1
    on both polarities, so the wrong table is an illegible cue."""
    category_list = List(
        id="L1",
        name="Explore: AI",
        slug="explore-ai",
        intent="Explore",
        category="AI",
    )
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("example-owner/ghstars", list_ids=["L1"])])
    store.save_lists([category_list])
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text('[category_colours]\nAI = "magenta"\n')

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.theme = "textual-light"
        app._refresh_table()
        await pilot.pause()
        membership: object = _table(app).get_row_at(0)[4]

    assert isinstance(membership, Text)
    assert str(membership) == "[🌐 Explore · AI]"
    assert any(
        str(span.style) == CATEGORY_COLOURS_LIGHT["magenta"]
        for span in membership.spans
    )


async def test_general_list_membership_renders_muted_with_its_name(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A List with no Intent and no Category keeps its own name and takes
    the theme's muted foreground, not a hashed colour."""
    general_list = List(id="L1", name="Tools", slug="tools")
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars", list_ids=["L1"])])
    store.save_lists([general_list])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        membership: object = _table(app).get_row_at(0)[4]
        muted = app.get_css_variables()["foreground-muted"][:7]

    assert isinstance(membership, Text)
    assert "Tools" in str(membership)
    assert any(str(span.style) == muted for span in membership.spans)


async def test_stale_pending_list_ids_is_ignored_by_the_table(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """`tag_star()` no longer writes `pending_list_ids` (ticket 16) --
    the field is dormant, kept only for `sync()`'s fallback path (ADR
    0004). A leftover value from before the upgrade must not resurrect
    the old "[pending sync]" display; the table only ever shows
    `list_ids`, which is already live."""
    public_list = List(id="L2", name="Explore: Tool", slug="explore-tool")
    star = make_star("example-owner/ghstars", pending_list_ids=["L2"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([public_list])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        row = _table(app).get_row_at(0)

    assert "Explore: Tool" not in row[4]
    assert "pending sync" not in row[4]


async def test_rate_limit_bar_shows_remaining_after_mount(
    tmp_path: Path, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])
    client = FakeGitHubClient(
        rate_limit=RateLimitStatus(remaining=42, limit=5000, ok=True)
    )

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        text = app.query_one("#system-status", Static).render()

    assert "42" in str(text)
    assert "5000" in str(text)


async def test_rate_limit_bar_flags_when_not_ok(
    tmp_path: Path, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])
    client = FakeGitHubClient(
        rate_limit=RateLimitStatus(remaining=10, limit=5000, ok=False)
    )

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        status = app.query_one("#system-status", Static)
        has_low_class = "-low" in status.classes

    assert has_low_class


async def test_rate_limit_bar_shows_checking_state_before_first_fetch_resolves(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """The title row must not be blank while the first API call runs."""
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])
    release = Event()

    class BlockingRateLimitClient(FakeGitHubClient):
        def check_rate_limit(self) -> RateLimitStatus:
            release.wait(timeout=2)
            return super().check_rate_limit()

    app = TuiApp(client=BlockingRateLimitClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        text = str(app.query_one("#system-status", Static).render())
        release.set()
        await app.workers.wait_for_complete()

    assert "checking" in text.lower()
    assert text.strip() != ""


async def test_rate_limit_bar_shows_error_when_model_validate_raises(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """A `ValidationError` from `RateLimitResponse.model_validate` (e.g.
    GitHub returning a response shape `_graphql` doesn't wrap into
    `GitHubApiError`) must not leave the bar blank forever with no
    notification -- it must show an explicit error state."""
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])

    class RaisingRateLimitClient(FakeGitHubClient):
        def check_rate_limit(self) -> RateLimitStatus:
            RateLimitResponse.model_validate({})  # raises ValidationError
            raise AssertionError("model_validate should have raised")

    app = TuiApp(client=RaisingRateLimitClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        status = app.query_one("#system-status", Static)
        text = str(status.render())
        has_low_class = "-low" in status.classes

    assert "checking" not in text.lower()
    assert text.strip() != ""
    assert has_low_class


async def test_tui_launches_and_notifies_when_state_lock_is_held(
    tmp_path: Path, make_star: StarFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent `ghstars` command (e.g. `sync`) holding the state
    lock must not crash the TUI on mount -- it opens empty, with an
    error notification, instead of a raw `filelock.Timeout` traceback."""
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])

    def _raise_timeout(*args: object, **kwargs: object) -> list[Star]:
        raise Timeout(str(store.base_dir / ".lock"))

    monkeypatch.setattr(store, "load_stars", _raise_timeout)

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)

    assert table.row_count == 0


async def test_single_item_tag_pushes_immediately(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])
    client = FakeGitHubClient(stars=[star])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, ListPickerScreen)
        app.screen.query_one("#new-list-input", Input).value = "Explore: Foo"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        counts = str(app.query_one("#collection-status", Static).render())

    updated = next(
        s for s in store.load_stars() if s.full_name == "example-owner/ghstars"
    )
    new_list = next(lst for lst in store.load_lists() if lst.name == "Explore: Foo")
    assert updated.list_ids == [new_list.id]
    assert updated.pending_list_ids is None
    # Pushed for real on GitHub too, not just staged locally.
    assert client.fetch_stars()[0].list_ids == [new_list.id]
    assert "Lists: 1" in counts
    assert "Unclassified: 0" in counts


async def test_bulk_tag_applies_to_every_selected_star(
    tmp_path: Path, make_star: StarFactory
) -> None:
    target = List(id="L_target", name="Explore: Foo", slug="explore-foo")
    star_a = make_star("example-owner/a")
    star_b = make_star("example-owner/b")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    store.save_lists([target])
    client = FakeGitHubClient(stars=[star_a, star_b], lists=[target])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        table.focus()
        # Both rows are sorted by full_name: example-owner/a, example-owner/b.
        await pilot.press("space")  # select row 0 (example-owner/a)
        await pilot.press("down")
        await pilot.press("space")  # select row 1 (example-owner/b)
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, ListPickerScreen)
        picker_table = app.screen.query_one("#picker-table", DataTable)
        picker_table.focus()
        await pilot.press("enter")  # select the existing "Explore: Foo" row
        await app.workers.wait_for_complete()
        await pilot.pause()

    stars = {s.full_name: s for s in store.load_stars()}
    assert stars["example-owner/a"].list_ids == ["L_target"]
    assert stars["example-owner/b"].list_ids == ["L_target"]


async def test_bulk_tag_batches_node_id_lookups_but_single_tag_does_not(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Ticket 16: more than one target resolves every node ID in one
    batched call up front; a single target skips it entirely (no
    batching win for one repo, matches tag_star()'s own default path)."""

    class _SpyClient(FakeGitHubClient):
        def __init__(self, stars: list[Star], lists: list[List]) -> None:
            super().__init__(stars=stars, lists=lists)
            self.batch_lookup_calls: list[list[str]] = []

        def resolve_repository_node_ids(self, full_names: list[str]) -> dict[str, str]:
            self.batch_lookup_calls.append(list(full_names))
            return super().resolve_repository_node_ids(full_names)

    target = List(id="L_target", name="Explore: Foo", slug="explore-foo")
    star_a = make_star("example-owner/a")
    star_b = make_star("example-owner/b")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    store.save_lists([target])
    client = _SpyClient(stars=[star_a, star_b], lists=[target])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        table.focus()
        await pilot.press("space")  # select row 0 (example-owner/a)
        await pilot.press("down")
        await pilot.press("space")  # select row 1 (example-owner/b)
        await pilot.press("t")
        await pilot.pause()
        picker_table = app.screen.query_one("#picker-table", DataTable)
        picker_table.focus()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

    assert len(client.batch_lookup_calls) == 1
    assert sorted(client.batch_lookup_calls[0]) == [
        "example-owner/a",
        "example-owner/b",
    ]

    client.batch_lookup_calls.clear()
    app2 = TuiApp(client=client, store=store)
    async with app2.run_test() as pilot:
        await pilot.pause()
        _table(app2).focus()
        await pilot.press("t")
        await pilot.pause()
        picker_table = app2.screen.query_one("#picker-table", DataTable)
        picker_table.focus()
        await pilot.press("enter")
        await app2.workers.wait_for_complete()
        await pilot.pause()

    assert client.batch_lookup_calls == []


async def test_toggle_select_preserves_cursor_position(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Regression test (code review finding): `action_toggle_select` must
    not rebuild the whole table (`DataTable.clear()` resets the cursor
    to row 0), or a "move down, select, move down, select" bulk
    selection silently lands on the wrong rows after the first toggle.
    """
    stars = [make_star(f"example-owner/{name}") for name in ("a", "b", "c", "d")]
    store = StateStore(tmp_path)
    store.save_stars(stars)
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        table.focus()
        # Rows sorted by full_name: a, b, c, d.
        await pilot.press("down")  # row 1 (b)
        await pilot.press("down")  # row 2 (c)
        await pilot.press("space")  # select c; cursor must stay on row 2
        assert table.cursor_row == 2
        await pilot.press("down")  # must move to row 3 (d), not row 1
        assert table.cursor_row == 3
        await pilot.press("space")  # select d
        selected = set(app._selected)

    assert selected == {"example-owner/c", "example-owner/d"}


async def test_retag_moves_star_between_intents_in_same_category(
    tmp_path: Path, make_star: StarFactory
) -> None:
    current = List(
        id="L_current",
        name="Current: Tool",
        slug="current-tool",
        items=["example-owner/ghstars"],
    )
    retired = List(id="L_retired", name="Retired: Tool", slug="retired-tool")
    star = make_star("example-owner/ghstars", list_ids=["L_current"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([current, retired])
    client = FakeGitHubClient(stars=[star], lists=[current, retired])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        await pilot.press("t")
        await pilot.pause()
        picker_table = app.screen.query_one("#picker-table", DataTable)
        picker_table.focus()
        # Current sorts before Retired alphabetically.
        await pilot.press("down")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

    updated = next(
        s for s in store.load_stars() if s.full_name == "example-owner/ghstars"
    )
    assert updated.list_ids == ["L_retired"]


async def test_double_tag_press_does_not_stack_two_pickers(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Regression test (code review finding): a fast double `t` press,
    both dispatched before the first `_open_picker` worker reaches
    `push_screen_wait`, must not schedule two picker screens.
    """
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        app.action_tag_selected()
        app.action_tag_selected()
        await pilot.pause()
        screen_count = len(app.screen_stack)

    assert screen_count == 2  # the base screen, plus exactly one picker


async def test_lists_overview_shows_public_and_private_explicitly(
    tmp_path: Path, make_star: StarFactory
) -> None:
    public_list = List(id="L_pub", name="Reference: Docs", slug="reference-docs")
    private_list = List(
        id="L_priv", name="Current: Secret", slug="current-secret", is_private=True
    )
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])
    store.save_lists([public_list, private_list])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        await pilot.press("l")
        await pilot.pause()
        overview = app.screen.query_one("#overview-table", DataTable)
        rows = [overview.get_row_at(i) for i in range(overview.row_count)]

    by_name = {str(row[0]): row for row in rows}
    assert _visibility_label(False) in by_name["Reference: Docs"][3]
    assert _visibility_label(True) in by_name["Current: Secret"][3]


async def test_tag_with_no_star_selected_does_not_open_the_picker(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path)
    app = TuiApp(client=FakeGitHubClient(), store=store)

    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        await pilot.press("t")
        await pilot.pause()
        screen_count = len(app.screen_stack)

    # An empty table provides no target for the picker.
    assert screen_count == 1


async def test_detail_pane_shows_full_record_of_star_under_cursor(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Ticket 22 / spec story 59: every Star field the local state store
    holds, including description and html_url which the table never
    shows, appears in the detail pane for the highlighted row."""
    lst = List(id="L1", name="Current: Tool", slug="current-tool", is_private=True)
    star = make_star(
        "example-owner/ghstars",
        description="A star-tracking tool",
        language="Python",
        license="MIT",
        stargazer_count=7,
        fork=True,
        follow=True,
        archived=False,
        list_ids=["L1"],
    )
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([lst])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        text = _detail_text(app)

    assert star.full_name in text
    assert star.html_url in text
    assert star.description is not None
    assert star.description in text
    assert "Python" in text
    assert "MIT" in text
    assert "7" in text
    assert "True" in text  # fork / follow
    assert _format_date(star.starred_at) in text
    assert _format_date(star.first_seen) in text
    assert _format_date(star.last_checked) in text
    assert "Current: Tool" in text
    assert _visibility_label(True) in text
    assert "none pending" in text  # pending_list_ids is None by default


async def test_detail_pane_updates_when_cursor_moves_to_a_different_star(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star_a = make_star("example-owner/a", description="First star")
    star_b = make_star("example-owner/b", description="Second star")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        table.focus()
        # Rows sort by full name.
        assert "First star" in _detail_text(app)
        await pilot.press("down")
        assert "Second star" in _detail_text(app)
        assert "First star" not in _detail_text(app)


async def test_detail_pane_renders_before_rate_limit_worker_completes(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """The detail pane must never block the initial paint on a live
    GitHub call -- it renders purely from already-loaded local state."""
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars", description="Local only")])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        # The detail pane must render before the rate-limit worker completes.
        text = _detail_text(app)

    assert "Local only" in text


async def test_detail_pane_updates_after_tagging_star_with_cursor_on_first_row(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Regression test (code review finding): `DataTable.clear()` only
    posts `RowHighlighted` when the cursor coordinate actually changes.
    With the cursor left on row 0 (the default, common case), tagging
    that star must still refresh the detail pane -- not rely on an
    event that `_refresh_table()`'s `table.clear()` won't fire here.
    """
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])
    client = FakeGitHubClient(stars=[star])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "Lists: none" in _detail_text(app)
        _table(app).focus()  # cursor stays on row 0
        await pilot.press("t")
        await pilot.pause()
        app.screen.query_one("#new-list-input", Input).value = "Explore: Foo"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        text = _detail_text(app)

    assert "Explore: Foo" in text
    assert "Lists: none" not in text


async def test_detail_pane_shows_placeholder_when_table_is_empty(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path)
    app = TuiApp(client=FakeGitHubClient(), store=store)

    async with app.run_test() as pilot:
        await pilot.pause()
        text = _detail_text(app)

    assert "No star selected" in text


async def test_detail_pane_visible_by_default_and_toggles_with_d(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """The detail pane is visible by default; "d"
    (action_toggle_detail_pane) hides/shows it on demand."""
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.query_one("#detail-pane", DetailPane).display is True

        await pilot.press("d")
        assert app.query_one("#detail-pane", DetailPane).display is False

        await pilot.press("d")
        assert app.query_one("#detail-pane", DetailPane).display is True


async def test_detail_pane_toggle_persists_across_quit(
    tmp_path: Path, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])
    store.save_lists([])
    state_path = tmp_path / "tui-state.toml"

    app = TuiApp(client=FakeGitHubClient(), store=store, state_path=state_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.press("q")

    assert load_tui_state(state_path).detail_pane_visible is False


async def test_sync_runs_only_after_explicit_key_and_reports_completion(
    tmp_path: Path, make_star: StarFactory
) -> None:
    stale = make_star("example-owner/stale")
    fresh = make_star("example-owner/fresh")
    store = StateStore(tmp_path)
    store.save_stars([stale])
    store.save_lists([])
    client = FakeGitHubClient(stars=[fresh])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "idle" in str(app.query_one("#system-status", Static).render())
        app._show_sync_stage("fetching Stars")
        assert "fetching Stars" in str(app.query_one("#system-status", Static).render())
        await pilot.press("y")
        await app.workers.wait_for_complete()
        await pilot.pause()
        status = str(app.query_one("#system-status", Static).render())
        counts = str(app.query_one("#collection-status", Static).render())

    assert "complete" in status
    assert "Stars: 1/1" in counts
    saved = {star.full_name: star for star in store.load_stars()}
    assert "example-owner/fresh" in saved
    assert saved["example-owner/stale"].archived is True


async def test_unstar_confirm_calls_remove_star_and_archives_locally(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])
    client = FakeGitHubClient(stars=[star])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        await pilot.press("u")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmUnstarScreen)
        await pilot.click("#confirm")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # Archived stars are filtered from the table.
        assert _table(app).row_count == 0
        counts = str(app.query_one("#collection-status", Static).render())

    assert "Stars: 0/0" in counts
    assert "example-owner/ghstars" not in {s.full_name for s in client.fetch_stars()}
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["example-owner/ghstars"].archived is True


async def test_unstar_cancel_leaves_star_untouched(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])
    client = FakeGitHubClient(stars=[star])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        await pilot.press("u")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmUnstarScreen)
        await pilot.click("#cancel")
        await pilot.pause()

    assert "example-owner/ghstars" in {s.full_name for s in client.fetch_stars()}
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["example-owner/ghstars"].archived is False


async def test_open_in_browser_launches_html_url(
    tmp_path: Path, make_star: StarFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    star = make_star("example-owner/ghstars")
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])

    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", opened.append)

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        await pilot.press("o")

    assert opened == [star.html_url]


async def test_sort_defaults_to_star_date_descending_and_s_toggles_to_name(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Spec story 57: star date descending (newest first) is the
    default sort -- the triage order. "s" toggles to name and back.
    Fixture is deliberately name-vs-date-discordant (the
    later-alphabetical repo was starred earlier) so a passing
    assertion actually proves which key is active, not a coincidence."""
    star_b_older = make_star(
        "example-owner/b", starred_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    star_a_newer = make_star(
        "example-owner/a", starred_at=datetime(2026, 6, 1, tzinfo=UTC)
    )
    store = StateStore(tmp_path)
    store.save_stars([star_b_older, star_a_newer])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        # Newest starred date sorts first by default.
        assert table.get_row_at(0)[1] == "example-owner/a"
        assert table.get_row_at(1)[1] == "example-owner/b"

        await pilot.press("s")  # -> name (alphabetical ascending)
        assert table.get_row_at(0)[1] == "example-owner/a"
        assert table.get_row_at(1)[1] == "example-owner/b"

        # Five more presses complete the sort cycle.
        for _ in range(5):
            await pilot.press("s")
        assert table.get_row_at(0)[1] == "example-owner/a"
        assert table.get_row_at(1)[1] == "example-owner/b"


async def test_sort_by_stargazer_count_language_and_list_count(
    tmp_path: Path, make_star: StarFactory
) -> None:
    lst = List(id="L1", name="Explore: Tool", slug="explore-tool")
    star_low = make_star(
        "example-owner/low", stargazer_count=5, language="Zig", list_ids=[]
    )
    star_high = make_star(
        "example-owner/high", stargazer_count=500, language="Ada", list_ids=["L1"]
    )
    store = StateStore(tmp_path)
    store.save_stars([star_low, star_high])
    store.save_lists([lst])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        await pilot.press("s")  # -> name
        await pilot.press("s")  # -> stargazer_desc
        assert table.get_row_at(0)[1] == "example-owner/high"
        assert table.get_row_at(1)[1] == "example-owner/low"

        await pilot.press("s")  # -> language (alphabetical: Ada, Zig)
        assert table.get_row_at(0)[1] == "example-owner/high"
        assert table.get_row_at(1)[1] == "example-owner/low"

        await pilot.press("s")  # -> list_count_desc
        assert table.get_row_at(0)[1] == "example-owner/high"
        assert table.get_row_at(1)[1] == "example-owner/low"


async def test_bottom_status_sort_label_shows_active_mode_and_toggles(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """The bottom status bar tracks the active sort mode."""
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        controls = app.query_one("#discovery-controls", Static)
        assert "Sort: Date" in str(controls.render())
        await pilot.press("s")
        assert "Sort: Name" in str(controls.render())


async def test_g_opens_a_labeled_config_form(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")
    store.save_stars([])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.press("g")
        await pilot.pause()

        config_screen = app.screen
        assert isinstance(config_screen, ConfigEditorScreen)
        labels = {str(label.render()) for label in config_screen.walk_children(Label)}
        assert {"Header height", "Date format", "Toast timeout", "Columns"} <= labels
        assert config_screen.query_one("#config-header_height", Input).has_class(
            "config-input"
        )
        config_scroll = config_screen.query_one("#config-scroll")
        config_help = config_screen.query_one("#config-help")
        assert config_scroll not in config_help.ancestors
        config_scroll.scroll_end(animate=False)
        await pilot.pause()
        assert config_help.visible
        assert "Esc Save" in str(config_help.render())
        assert "x Discard" in str(config_help.render())
        assert app.focused is not None
        assert app.focused.id == "config-header_height"
        await pilot.press("tab")
        assert app.focused is not None
        assert app.focused.id == "config-date_format"


async def test_config_x_discards_and_q_does_not_quit(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    original = "# keep this comment\nheader_height = 1\n"
    config_path.write_text(original)
    store = StateStore(tmp_path / "state")
    store.save_stars([])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test() as pilot:
        await pilot.press("g")
        await pilot.press("q")
        config_screen = app.screen
        assert isinstance(config_screen, ConfigEditorScreen)
        config_screen.query_one("#config-header_height", Input).value = "3"
        await pilot.press("x")
        await pilot.pause()

        assert app.screen is not config_screen
        assert config_path.read_text() == original


async def test_config_escape_saves_valid_changes(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text("# keep this comment\nheader_height = 1\n")
    store = StateStore(tmp_path / "state")
    store.save_stars([])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test() as pilot:
        await pilot.press("g")
        app.screen.query_one("#config-header_height", Input).value = "3"
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, ConfigEditorScreen)
        assert load_tui_config(config_path).header_height == 3
        assert "# keep this comment" in config_path.read_text()
        assert any(
            "Restart ghstars" in notification.message
            for notification in app._notifications
        )


async def test_config_escape_keeps_invalid_form_open(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    original = "header_height = 1\n"
    config_path.write_text(original)
    store = StateStore(tmp_path / "state")
    store.save_stars([])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test() as pilot:
        await pilot.press("g")
        app.screen.query_one("#config-header_height", Input).value = "0"
        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, ConfigEditorScreen)
        assert config_path.read_text() == original
        assert any(
            "Invalid configuration" in notification.message
            for notification in app._notifications
        )


async def test_bottom_status_shows_compact_action_keys(
    tmp_path: Path, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/ghstars")])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        actions = str(app.query_one("#action-controls", Static).render())

    assert all(
        label in actions
        for label in (
            "[t] Tag",
            "[d] Detail",
            "[spc] Select",
            "[g] Config",
            "[q] Quit",
        )
    )


async def test_discovery_rows_show_controls_counts_and_clickable_membership(
    tmp_path: Path, make_star: StarFactory
) -> None:
    ai = List(
        id="L_ai",
        name="Explore: AI",
        slug="explore-ai",
        intent="Explore",
        category="AI",
    )
    classified = make_star("example-owner/classified", list_ids=["L_ai"])
    unclassified = make_star("example-owner/unclassified", list_ids=[])
    store = StateStore(tmp_path)
    store.save_stars([classified, unclassified])
    store.save_lists([ai])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        controls_widget = app.query_one("#discovery-controls", Static)
        controls = str(controls_widget.render())
        counts = str(app.query_one("#collection-status", Static).render())
        assert controls_widget.parent is not None
        controls_parent_id = controls_widget.parent.id
        membership: object = _table(app).get_row_at(0)[4]
        handled = await app.run_action("app.filter_membership('L_ai')", app)
        await pilot.pause()
        filtered_names = [
            str(_table(app).get_row_at(index)[1])
            for index in range(_table(app).row_count)
        ]

    assert controls_parent_id == "bottom-status-row"
    assert all(label in controls for label in ("Search", "Filter: All", "Sort: Date"))
    assert all(
        label in counts
        for label in ("Stars: 2/2", "Lists: 1", "Unclassified: 1", "Pending: 0")
    )
    assert isinstance(membership, Text)
    assert any(
        span.style.meta.get("@click") == "app.filter_membership('L_ai')"
        for span in membership.spans
        if isinstance(span.style, Style)
    )
    assert handled is True
    assert filtered_names == ["example-owner/classified"]


async def test_table_renders_the_active_preset_columns_in_order(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """`columns` is ordered: the list sets which optional columns show
    and in what order (ADR 0008)."""
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        '[layouts.compact]\ncolumns = ["Owner", "Archived", "Stars", "Language"]\n'
    )
    store = StateStore(tmp_path / "state")
    store.save_stars(
        [make_star("example-owner/repo", language="Python", stargazer_count=42)]
    )
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        columns = [str(column.label) for column in _table(app).columns.values()]
        row = [str(cell) for cell in _table(app).get_row_at(0)]

    assert columns == ["Sel", "Star", "Owner", "Archived", "Stars", "Language"]
    assert row == ["[ ]", "example-owner/repo", "example-owner", "no", "42", "Python"]


async def test_preset_without_optional_columns_still_shows_sel_and_star(
    tmp_path: Path, make_star: StarFactory
) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text("[layouts.compact]\ncolumns = []\n")
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("example-owner/repo")])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        columns = [str(column.label) for column in _table(app).columns.values()]
        row = [str(cell) for cell in _table(app).get_row_at(0)]

    assert columns == ["Sel", "Star"]
    assert row == ["[ ]", "example-owner/repo"]


async def test_narrow_terminal_hides_no_column(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """ADR 0008 overrides ticket 28: the table keeps every configured
    column and scrolls instead of hiding one."""
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/repo", language="Python")])
    store.save_lists([])

    async def _columns(width: int) -> list[str]:
        app = TuiApp(client=FakeGitHubClient(), store=store)
        async with app.run_test(size=(width, 24)) as pilot:
            await pilot.pause()
            return [str(column.label) for column in _table(app).columns.values()]

    assert await _columns(80) == await _columns(200)
    assert "Membership" in await _columns(80)


async def test_detail_pane_visibility_ignores_terminal_width(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """The layout preset and the user's toggle control the pane. Terminal
    width no longer hides it (ADR 0008)."""
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("example-owner/repo")])
    store.save_lists([])
    hidden_config = tmp_path / "hidden" / "tui.toml"
    hidden_config.parent.mkdir()
    hidden_config.write_text("[layouts.compact]\ndetail_pane_visible = false\n")

    narrow = TuiApp(client=FakeGitHubClient(), store=store)
    async with narrow.run_test(size=(60, 24)) as pilot:
        await pilot.pause()
        narrow_visible = narrow.query_one("#detail-pane", DetailPane).display

    wide = TuiApp(client=FakeGitHubClient(), store=store, config_path=hidden_config)
    async with wide.run_test(size=(200, 40)) as pilot:
        await pilot.pause()
        wide_visible = wide.query_one("#detail-pane", DetailPane).display

    assert narrow_visible is True
    assert wide_visible is False


async def test_configured_date_format_applies_to_table_and_detail_pane(
    tmp_path: Path, make_star: StarFactory
) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        'date_format = "%Y-%m-%d"\n\n[layouts.compact]\ncolumns = ["Starred at"]\n'
    )
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("example-owner/repo")])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cell = str(_table(app).get_row_at(0)[2])
        detail = _detail_text(app)

    assert cell == "2026-08-16"
    assert "2026-08-16" in detail
    assert "16-Aug-2026" not in detail


async def test_configured_toast_timeout_applies_to_error_toasts(
    tmp_path: Path, make_star: StarFactory
) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text("toast_timeout = 3\n")
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("example-owner/repo")])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._show_sync_error("boom")
        await pilot.pause()
        timeouts = [n.timeout for n in app._notifications]

    assert timeouts == [3]


async def test_ascii_only_replaces_glyphs_with_text_markers(
    tmp_path: Path, make_star: StarFactory
) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text("ascii_only = true\n")
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("example-owner/repo", list_ids=["L1"])])
    store.save_lists(
        [List(id="L1", name="Current: Tool", slug="current-tool", is_private=True)]
    )

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        title = str(app.query_one("#title-label", Static).render())
        api_status = app._api_status
        sync_status = app._sync_status
        detail = _detail_text(app)

    assert title == "* ghstars"
    assert api_status.startswith("?")
    assert sync_status == "o idle"
    assert _visibility_label(True, ascii_only=True) in detail
    assert "\U0001f512" not in detail


async def test_ascii_only_replaces_membership_chip_glyphs(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """The table's Membership column goes through `_membership_chips`,
    a separate render path from the detail pane's `_visibility_label` --
    `ascii_only` must reach both."""
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text("ascii_only = true\n")
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("example-owner/repo", list_ids=["L1"])])
    store.save_lists(
        [List(id="L1", name="Current: Tool", slug="current-tool", is_private=True)]
    )

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        row = _table(app).get_row_at(0)

    row_text = " ".join(str(cell) for cell in row)
    assert "P" in row_text
    assert "\U0001f512" not in row_text


async def test_show_clock_adds_a_clock_only_when_configured(
    tmp_path: Path, make_star: StarFactory
) -> None:
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text("show_clock = true\n")
    store = StateStore(tmp_path / "state")
    store.save_stars([make_star("example-owner/repo")])
    store.save_lists([])

    with_clock = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with with_clock.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        clock = str(with_clock.query_one("#clock", Static).render())

    without_clock = TuiApp(client=FakeGitHubClient(), store=store)
    async with without_clock.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        missing = without_clock.query("#clock")

    assert re.fullmatch(r"\d{2}:\d{2}", clock)
    assert not missing


async def test_default_filter_applies_when_state_holds_no_filter(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """State's `filter` is `None` on a first launch and after the user
    clears it; config's `default_filter` fills that gap either time."""
    config_path = tmp_path / "config" / "tui.toml"
    config_path.parent.mkdir()
    config_path.write_text('default_filter = "unclassified"\n')
    store = StateStore(tmp_path / "state")
    store.save_stars(
        [
            make_star("example-owner/classified", list_ids=["L1"]),
            make_star("example-owner/unclassified"),
        ]
    )
    store.save_lists([List(id="L1", name="Explore: AI", slug="explore-ai")])

    app = TuiApp(client=FakeGitHubClient(), store=store, config_path=config_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        names = [
            str(_table(app).get_row_at(index)[1])
            for index in range(_table(app).row_count)
        ]
        controls = str(app.query_one("#discovery-controls", Static).render())

    assert names == ["example-owner/unclassified"]
    assert "Filter: Unclassified (no List)" in controls


async def test_unclassified_count_action_applies_quick_filter(
    tmp_path: Path, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars(
        [
            make_star("example-owner/classified", list_ids=["L1"]),
            make_star("example-owner/unclassified"),
        ]
    )
    store.save_lists([List(id="L1", name="Explore: AI", slug="explore-ai")])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        handled = await app.run_action("app.filter_unclassified", app)
        await pilot.pause()
        names = [
            str(_table(app).get_row_at(index)[1])
            for index in range(_table(app).row_count)
        ]

    assert handled is True
    assert names == ["example-owner/unclassified"]


async def test_filters_by_category_intent_list_and_unclassified(
    tmp_path: Path, make_star: StarFactory
) -> None:
    explore = List(
        id="L1", name="Explore: AI", slug="explore-ai", category="AI", intent="Explore"
    )
    current = List(
        id="L2",
        name="Current: Tools",
        slug="current-tools",
        category="Tools",
        intent="Current",
    )
    star_explore = make_star(
        "example-owner/explore", list_ids=["L1"], language="Python"
    )
    star_current = make_star("example-owner/current", list_ids=["L2"], language="Go")
    star_none = make_star("example-owner/none", list_ids=[])
    store = StateStore(tmp_path)
    store.save_stars([star_explore, star_current, star_none])
    store.save_lists([explore, current])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, FilterScreen)
        await pilot.press("a", "i", "enter")  # Search for AI
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "example-owner/explore"

        await pilot.press("/")
        search = app.query_one("#search-input", Input)
        search.value = "current"
        await pilot.pause()
        assert table.row_count == 0
        await pilot.press("escape")

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        await pilot.press("c", "u", "r", "r", "e", "n", "t", "enter")
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "example-owner/current"

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("c", "u", "r", "r", "e", "n", "t", "enter")
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "example-owner/current"

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "example-owner/none"
        assert app._state.filter == "unclassified"

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert table.row_count == 3

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.press("g", "o", "enter")  # Search for Go
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "example-owner/current"


async def test_visible_rows_matches_a_direct_query_stars_call(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Ticket 31 Scope E: the TUI must not reimplement Filter/Sort/search
    -- it calls `ghstars.core.discovery.query_stars()` through
    `_visible_rows()`. Prove the two agree for the same Filter/sort/
    search inputs, rather than trusting that `_visible_rows()`'s
    implementation still forwards to `query_stars` by inspection alone.
    """
    explore = List(
        id="L1", name="Explore: AI", slug="explore-ai", category="AI", intent="Explore"
    )
    star_explore = make_star(
        "example-owner/explore", list_ids=["L1"], language="Python"
    )
    star_other = make_star("example-owner/other", list_ids=[], language="Go")
    store = StateStore(tmp_path)
    store.save_stars([star_explore, star_other])
    store.save_lists([explore])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        await pilot.press("a", "i", "enter")  # Filter by Category "AI"

        tui_rows = app._visible_rows()

        direct_rows = query_stars(
            app._stars,
            app._lists,
            filters=[app._filter_key] if app._filter_key else [],
            search=app._search_query,
            sort=app._CORE_SORT[app._sort_mode],
        )

        assert [row.star.full_name for row in tui_rows] == [
            row.star.full_name for row in direct_rows
        ]
        assert [row.star.full_name for row in tui_rows] == ["example-owner/explore"]


async def test_filter_search_selects_best_match_and_all_is_explicit(
    tmp_path: Path, make_star: StarFactory
) -> None:
    ai = List(id="L1", name="Explore: AI", slug="explore-ai", category="AI")
    tools = List(id="L2", name="Explore: Tools", slug="explore-tools", category="Tools")
    store = StateStore(tmp_path)
    store.save_stars(
        [
            make_star("example-owner/ai", list_ids=["L1"]),
            make_star("example-owner/tools", list_ids=["L2"]),
        ]
    )
    store.save_lists([ai, tools])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        filter_table = app.screen.query_one("#filter-table", DataTable)
        # The clear option shows without a search, and always ranks last
        # so that Enter never clears the filter by accident.
        assert [
            str(filter_table.get_row_at(i)[0]) for i in range(filter_table.row_count)
        ] == [
            "AI",
            "Tools",
            "All categories",
        ]
        query = app.screen.query_one("#filter-query", Input)
        query.value = "to"
        await pilot.pause()
        assert str(filter_table.get_row_at(0)[0]) == "Tools"
        await pilot.press("enter")
        assert _table(app).row_count == 1
        assert _table(app).get_row_at(0)[1] == "example-owner/tools"

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        query = app.screen.query_one("#filter-query", Input)
        query.value = "all categories"
        await pilot.pause()
        filter_table = app.screen.query_one("#filter-table", DataTable)
        assert str(filter_table.get_row_at(0)[0]) == "All categories"
        await pilot.press("enter")
        await pilot.pause()
        assert _table(app).row_count == 2


async def test_filter_search_ranks_exact_before_prefix_before_substring(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """An exact match wins, then a prefix match, then any substring."""
    lists = [
        List(id="L1", name="Explore: Go", slug="explore-go", category="Go"),
        List(id="L2", name="Explore: Gopher", slug="explore-gopher", category="Gopher"),
        List(id="L3", name="Explore: Django", slug="explore-django", category="Django"),
    ]
    store = StateStore(tmp_path)
    store.save_stars([make_star("example-owner/a", list_ids=["L1"])])
    store.save_lists(lists)

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        query = app.screen.query_one("#filter-query", Input)
        query.value = "go"
        await pilot.pause()
        filter_table = app.screen.query_one("#filter-table", DataTable)
        assert [
            str(filter_table.get_row_at(i)[0]) for i in range(filter_table.row_count)
        ] == [
            "Go",  # exact
            "Gopher",  # prefix
            "Django",  # substring
            # "All categories" also holds "go", inside "categories". The
            # clear option always ranks last, so it never steals Enter.
            "All categories",
        ]


async def test_filter_search_handles_multiple_zero_and_empty_queries(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Enter applies the best-ranked match. Zero matches leave the
    screen open, because there is nothing to apply.
    """
    lists = [
        List(id="L1", name="Explore: Tools", slug="explore-tools", category="Tools"),
        List(id="L2", name="Explore: Toys", slug="explore-toys", category="Toys"),
    ]
    store = StateStore(tmp_path)
    store.save_stars(
        [
            make_star("example-owner/tools", list_ids=["L1"]),
            make_star("example-owner/toys", list_ids=["L2"]),
        ]
    )
    store.save_lists(lists)

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        filter_table = app.screen.query_one("#filter-table", DataTable)
        query = app.screen.query_one("#filter-query", Input)

        # Zero matches: no rows, and Enter leaves the screen open.
        query.value = "zzz"
        await pilot.pause()
        assert filter_table.row_count == 0
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.query("#filter-table")

        # Multiple matches: both rows show, ranked alphabetically, and
        # Enter applies the first one.
        query.value = "to"
        await pilot.pause()
        assert [
            str(filter_table.get_row_at(i)[0]) for i in range(filter_table.row_count)
        ] == ["Tools", "Toys"]
        await pilot.press("enter")
        await pilot.pause()
        assert _table(app).row_count == 1
        assert _table(app).get_row_at(0)[1] == "example-owner/tools"


async def test_metadata_filters_support_owner_fork_and_followed(
    tmp_path: Path, make_star: StarFactory
) -> None:
    owned = make_star("alice/tool", fork=True, follow=True, license="MIT")
    other = make_star("bob/library", license="Apache-2.0")
    store = StateStore(tmp_path)
    store.save_stars([owned, other])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("k")
        await pilot.pause()
        await pilot.press("enter")
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "alice/tool"

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("enter")
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "alice/tool"

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        await pilot.press("a", "l", "i", "c", "e", "enter")
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "alice/tool"

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        await pilot.press("m", "i", "t", "enter")  # Search for MIT
        assert table.row_count == 1
        assert table.get_row_at(0)[1] == "alice/tool"


async def test_recency_filter_supports_recent_and_older_ranges(
    tmp_path: Path, make_star: StarFactory
) -> None:
    now = datetime.now(UTC)
    recent = make_star("example-owner/recent", starred_at=now - timedelta(hours=12))
    old = make_star("example-owner/old", starred_at=now - timedelta(days=400))
    store = StateStore(tmp_path)
    store.save_stars([recent, old])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        await pilot.press("d")  # Recency shortcut: last 1 day
        assert _table(app).row_count == 1
        assert _table(app).get_row_at(0)[1] == "example-owner/recent"

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        await pilot.press("o")  # Recency shortcut: older than 1 year
        assert _table(app).row_count == 1
        assert _table(app).get_row_at(0)[1] == "example-owner/old"


async def test_search_matches_name_and_description_as_you_type(
    tmp_path: Path, make_star: StarFactory
) -> None:
    named = make_star("example-owner/needle", description="A useful widget")
    described = make_star("example-owner/other", description="Contains the needle")
    store = StateStore(tmp_path)
    store.save_stars([named, described])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        search = app.query_one("#search-input", Input)
        search.value = "NEEDLE"
        await pilot.pause()
        assert _table(app).row_count == 2
        search.value = "widget"
        await pilot.pause()
        controls = str(app.query_one("#discovery-controls", Static).render())
        assert "Search: widget" in controls
        assert _table(app).row_count == 1
        assert _table(app).get_row_at(0)[1] == "example-owner/needle"


async def test_filter_persists_in_tui_state(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("example-owner/none", list_ids=[])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([])
    state_path = tmp_path / "tui-state.toml"

    app = TuiApp(client=FakeGitHubClient(), store=store, state_path=state_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        await pilot.press("q")

    assert load_tui_state(state_path).filter == "unclassified"


async def test_sort_by_list_name_ascending_no_lists_last(
    tmp_path: Path, make_star: StarFactory
) -> None:
    list_b = List(id="LB", name="Explore: Bravo", slug="explore-bravo")
    list_a = List(id="LA", name="Explore: Alpha", slug="explore-alpha")
    star_in_b = make_star("example-owner/in-b", list_ids=["LB"])
    star_in_a = make_star("example-owner/in-a", list_ids=["LA"])
    star_unclassified = make_star("example-owner/none", list_ids=[])
    store = StateStore(tmp_path)
    store.save_stars([star_in_b, star_in_a, star_unclassified])
    store.save_lists([list_a, list_b])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        for _ in range(5):  # starred_desc -> ... -> list_name
            await pilot.press("s")
        assert app._sort_mode == "list_name"
        assert table.get_row_at(0)[1] == "example-owner/in-a"
        assert table.get_row_at(1)[1] == "example-owner/in-b"
        assert table.get_row_at(2)[1] == "example-owner/none"
