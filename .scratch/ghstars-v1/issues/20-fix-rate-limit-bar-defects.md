# 20 — Fix TUI rate-limit-bar defects

**What to build:** `_fetch_rate_limit`'s worker (`tui/app.py:432`) catches only `GitHubApiError`. A `ValidationError` from `RateLimitResponse.model_validate` is not wrapped by `_graphql`, so it escapes the worker and leaves `RateLimitBar` blank forever with no notification. `RateLimitBar` is also constructed with no initial content, so it paints as a blank strip for the ~0.7s `check_rate_limit()` takes on a real call. Fix both. This is a live defect on `main`, independent of the rest of the TUI redesign.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `_fetch_rate_limit` catches the same broad `Exception` `_apply_tag` already documents catching, for the same reason, and reports any failure through `self.notify(..., severity="error")` — never a silent blank bar
- [ ] `RateLimitBar` shows a labelled "checking" state immediately on construction, before the first `check_rate_limit()` call returns
- [ ] A regression test forces `RateLimitResponse.model_validate` to raise and asserts the bar shows an error state, not blank
