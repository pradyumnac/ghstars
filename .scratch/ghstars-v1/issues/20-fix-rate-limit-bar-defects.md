# 20 — Fix TUI rate-limit-bar defects

**What to build:** `_fetch_rate_limit`'s worker (`tui/app.py:432`) catches only `GitHubApiError`. A `ValidationError` from `RateLimitResponse.model_validate` is not wrapped by `_graphql`, so it escapes the worker and leaves `RateLimitBar` blank forever with no notification. `RateLimitBar` is also constructed with no initial content, so it paints as a blank strip for the ~0.7s `check_rate_limit()` takes on a real call. Fix both. This is a live defect on `main`, independent of the rest of the TUI redesign.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `_fetch_rate_limit` catches the same broad `Exception` `_apply_tag` already documents catching, for the same reason, and reports any failure through `self.notify(..., severity="error")` — never a silent blank bar
- [x] `RateLimitBar` shows a labelled "checking" state immediately on construction, before the first `check_rate_limit()` call returns
- [x] A regression test forces `RateLimitResponse.model_validate` to raise and asserts the bar shows an error state, not blank

## Comments

- `_fetch_rate_limit` now catches `Exception` (was `GitHubApiError` only), with the same reasoning comment style as `_apply_tag`, and calls `self.notify(..., severity="error")` on failure in addition to updating the bar.
- `RateLimitBar.__init__` now seeds `Static`'s content with `"API rate limit: checking..."` instead of leaving it blank, so the bar is never an empty strip while the first fetch is in flight.
- While fixing this, found and fixed a real `MarkupError` crash: `RateLimitBar.show_unknown()` interpolated the raw exception `detail` into `Static.update()`, and a `pydantic.ValidationError`'s message routinely contains `[type=missing, ...]`-style text that Textual's markup parser rejects. Both `show_unknown()` and the new `self.notify(...)` call now escape `detail` via `textual.markup.escape`.
- Added two regression tests to `tests/test_tui.py`: one asserting `RateLimitBar`'s "checking" placeholder renders immediately on construction, and one that forces `RateLimitResponse.model_validate({})` to raise and asserts the mounted bar shows a non-blank error state with the `-low` class set.
- Full suite (`uv run pytest`) passes: 208 passed. `ruff format`, `ruff check --fix`, and `mypy` all clean.
- `/code-review` found no correctness issues; one theoretical nit (narrowed `RateLimitBar.__init__` drops `Static`'s other kwargs like `name`/`classes`) was left as-is since nothing in the codebase calls it with those kwargs.
