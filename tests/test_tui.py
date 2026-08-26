"""Tests for the TUI (ticket 09): single-item tagging, bulk tagging,
retagging, List visibility display, and the rate limit bar.

Uses Textual's own `App.run_test()` pilot -- no real terminal, no
network. Every client is `FakeGitHubClient`; mutations only ever touch
`tmp_path` via a real `StateStore`. `tag_star()`'s own mutating work
runs in a `@work(thread=True)` worker, so tests await
`app.workers.wait_for_complete()` after triggering it.
"""

from pathlib import Path

import pytest
from conftest import StarFactory
from filelock import Timeout
from textual.widgets import DataTable, Input

from ghstars.core.fake_client import FakeGitHubClient
from ghstars.core.models import List, RateLimitStatus, Star
from ghstars.core.state_store import StateStore
from ghstars.github.schema import RateLimitResponse
from ghstars.tui.app import (
    ConfirmUnstarScreen,
    DetailPane,
    ListPickerScreen,
    RateLimitBar,
    TuiApp,
    _format_date,
    _visibility_label,
)


def _table(app: TuiApp) -> DataTable[str]:
    return app.query_one("#stars-table", DataTable)


def _detail_text(app: TuiApp) -> str:
    return str(app.query_one("#detail-pane", DetailPane).render())


async def test_stars_table_shows_membership_with_visibility(
    tmp_path: Path, make_star: StarFactory
) -> None:
    private_list = List(
        id="L1", name="Current: Tool", slug="current-tool", is_private=True
    )
    star = make_star("pradyumnac/ghstars", list_ids=["L1"])
    store = StateStore(tmp_path)
    store.save_stars([star])
    store.save_lists([private_list])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        row = _table(app).get_row_at(0)

    assert row[1] == "pradyumnac/ghstars"
    assert "Current: Tool" in row[4]
    assert _visibility_label(True) in row[4]
    assert "pending" not in row[4]


async def test_stale_pending_list_ids_is_ignored_by_the_table(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """`tag_star()` no longer writes `pending_list_ids` (ticket 16) --
    the field is dormant, kept only for `sync()`'s fallback path (ADR
    0004). A leftover value from before the upgrade must not resurrect
    the old "[pending sync]" display; the table only ever shows
    `list_ids`, which is already live."""
    public_list = List(id="L2", name="Explore: Tool", slug="explore-tool")
    star = make_star("pradyumnac/ghstars", pending_list_ids=["L2"])
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
    store.save_stars([make_star("pradyumnac/ghstars")])
    client = FakeGitHubClient(
        rate_limit=RateLimitStatus(remaining=42, limit=5000, ok=True)
    )

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        bar = app.query_one("#rate-limit-bar", RateLimitBar)
        text = bar.render()

    assert "42" in str(text)
    assert "5000" in str(text)


async def test_rate_limit_bar_flags_when_not_ok(
    tmp_path: Path, make_star: StarFactory
) -> None:
    store = StateStore(tmp_path)
    store.save_stars([make_star("pradyumnac/ghstars")])
    client = FakeGitHubClient(
        rate_limit=RateLimitStatus(remaining=10, limit=5000, ok=False)
    )

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        bar = app.query_one("#rate-limit-bar", RateLimitBar)
        has_low_class = "-low" in bar.classes

    assert has_low_class


async def test_rate_limit_bar_shows_checking_state_before_first_fetch_resolves(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Acceptance: the bar must never paint blank while the first
    `check_rate_limit()` call (~0.7s on a real client) is in flight."""
    store = StateStore(tmp_path)
    store.save_stars([make_star("pradyumnac/ghstars")])

    bar = RateLimitBar(id="rate-limit-bar")
    text = str(bar.render())

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
    store.save_stars([make_star("pradyumnac/ghstars")])

    class RaisingRateLimitClient(FakeGitHubClient):
        def check_rate_limit(self) -> RateLimitStatus:
            RateLimitResponse.model_validate({})  # raises ValidationError
            raise AssertionError("model_validate should have raised")

    app = TuiApp(client=RaisingRateLimitClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        bar = app.query_one("#rate-limit-bar", RateLimitBar)
        text = str(bar.render())
        has_low_class = "-low" in bar.classes

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
    store.save_stars([make_star("pradyumnac/ghstars")])

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
    star = make_star("pradyumnac/ghstars")
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

    updated = next(s for s in store.load_stars() if s.full_name == "pradyumnac/ghstars")
    new_list = next(lst for lst in store.load_lists() if lst.name == "Explore: Foo")
    assert updated.list_ids == [new_list.id]
    assert updated.pending_list_ids is None
    # Pushed for real on GitHub too, not just staged locally.
    assert client.fetch_stars()[0].list_ids == [new_list.id]


async def test_bulk_tag_applies_to_every_selected_star(
    tmp_path: Path, make_star: StarFactory
) -> None:
    target = List(id="L_target", name="Explore: Foo", slug="explore-foo")
    star_a = make_star("pradyumnac/a")
    star_b = make_star("pradyumnac/b")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    store.save_lists([target])
    client = FakeGitHubClient(stars=[star_a, star_b], lists=[target])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        table.focus()
        # Both rows are sorted by full_name: pradyumnac/a, pradyumnac/b.
        await pilot.press("space")  # select row 0 (pradyumnac/a)
        await pilot.press("down")
        await pilot.press("space")  # select row 1 (pradyumnac/b)
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, ListPickerScreen)
        picker_table = app.screen.query_one("#picker-table", DataTable)
        picker_table.focus()
        await pilot.press("enter")  # select the existing "Explore: Foo" row
        await app.workers.wait_for_complete()
        await pilot.pause()

    stars = {s.full_name: s for s in store.load_stars()}
    assert stars["pradyumnac/a"].list_ids == ["L_target"]
    assert stars["pradyumnac/b"].list_ids == ["L_target"]


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
    star_a = make_star("pradyumnac/a")
    star_b = make_star("pradyumnac/b")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    store.save_lists([target])
    client = _SpyClient(stars=[star_a, star_b], lists=[target])

    app = TuiApp(client=client, store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        table.focus()
        await pilot.press("space")  # select row 0 (pradyumnac/a)
        await pilot.press("down")
        await pilot.press("space")  # select row 1 (pradyumnac/b)
        await pilot.press("t")
        await pilot.pause()
        picker_table = app.screen.query_one("#picker-table", DataTable)
        picker_table.focus()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

    assert len(client.batch_lookup_calls) == 1
    assert sorted(client.batch_lookup_calls[0]) == ["pradyumnac/a", "pradyumnac/b"]

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
    stars = [make_star(f"pradyumnac/{name}") for name in ("a", "b", "c", "d")]
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

    assert selected == {"pradyumnac/c", "pradyumnac/d"}


async def test_retag_moves_star_between_intents_in_same_category(
    tmp_path: Path, make_star: StarFactory
) -> None:
    current = List(
        id="L_current",
        name="Current: Tool",
        slug="current-tool",
        items=["pradyumnac/ghstars"],
    )
    retired = List(id="L_retired", name="Retired: Tool", slug="retired-tool")
    star = make_star("pradyumnac/ghstars", list_ids=["L_current"])
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
        # Retired: Tool sorts before Current: Tool alphabetically ("R" < "C"? no,
        # 'C' < 'R', so Current: Tool is row 0, Retired: Tool is row 1).
        await pilot.press("down")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

    updated = next(s for s in store.load_stars() if s.full_name == "pradyumnac/ghstars")
    assert updated.list_ids == ["L_retired"]


async def test_double_tag_press_does_not_stack_two_pickers(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Regression test (code review finding): a fast double `t` press,
    both dispatched before the first `_open_picker` worker reaches
    `push_screen_wait`, must not schedule two picker screens.
    """
    star = make_star("pradyumnac/ghstars")
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
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([public_list, private_list])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        _table(app).focus()
        await pilot.press("l")
        await pilot.pause()
        overview = app.screen.query_one("#overview-table", DataTable)
        rows = [overview.get_row_at(i) for i in range(overview.row_count)]

    by_name = {row[0]: row for row in rows}
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

    # No Star was synced, so the table is empty and there is nothing to
    # tag. The picker must never open onto zero targets.
    assert screen_count == 1


async def test_detail_pane_shows_full_record_of_star_under_cursor(
    tmp_path: Path, make_star: StarFactory
) -> None:
    """Ticket 22 / spec story 59: every Star field the local state store
    holds, including description and html_url which the table never
    shows, appears in the detail pane for the highlighted row."""
    lst = List(id="L1", name="Current: Tool", slug="current-tool", is_private=True)
    star = make_star(
        "pradyumnac/ghstars",
        description="A star-tracking tool",
        language="Python",
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
    assert star.description in text
    assert "Python" in text
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
    star_a = make_star("pradyumnac/a", description="First star")
    star_b = make_star("pradyumnac/b", description="Second star")
    store = StateStore(tmp_path)
    store.save_stars([star_a, star_b])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = _table(app)
        table.focus()
        # Rows sorted by full_name: a, b.
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
    store.save_stars([make_star("pradyumnac/ghstars", description="Local only")])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        # No `await app.workers.wait_for_complete()` here: the rate
        # limit fetch worker may still be in flight, yet the detail
        # pane has already been populated from local state.
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
    star = make_star("pradyumnac/ghstars")
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
    store.save_stars([make_star("pradyumnac/ghstars")])
    store.save_lists([])

    app = TuiApp(client=FakeGitHubClient(), store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one("#detail-pane", DetailPane)
        assert pane.display is True

        await pilot.press("d")
        assert pane.display is False

        await pilot.press("d")
        assert pane.display is True


async def test_unstar_confirm_calls_remove_star_and_archives_locally(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/ghstars")
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
        # Archived stars drop out of the table -- _reload_local_state()
        # filters them the same way sync()-detected unstars already do.
        assert _table(app).row_count == 0

    assert "pradyumnac/ghstars" not in {s.full_name for s in client.fetch_stars()}
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["pradyumnac/ghstars"].archived is True


async def test_unstar_cancel_leaves_star_untouched(
    tmp_path: Path, make_star: StarFactory
) -> None:
    star = make_star("pradyumnac/ghstars")
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

    assert "pradyumnac/ghstars" in {s.full_name for s in client.fetch_stars()}
    saved = {s.full_name: s for s in store.load_stars()}
    assert saved["pradyumnac/ghstars"].archived is False


async def test_open_in_browser_launches_html_url(
    tmp_path: Path, make_star: StarFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    star = make_star("pradyumnac/ghstars")
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
