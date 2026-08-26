# 02 — Real GitHub client: fetch stars

**What to build:** `ghstars.github`, the concrete client implementing `ghstars.core`'s abstract interface over `gh api graphql`, swapped into the CLI wiring from 01 in place of the fake. Fetches `viewer.starredRepositories` (paginated) for the base star list, plus `viewer.repositories(affiliations:[OWNER])` for fork status and `viewer.following` for follow status — both needed to populate the `Star` model's `fork`/`follow` fields, not just the obvious ones. A real rate-limit check runs before any fetch begins, so a large sync can't get stuck mid-way and leave state half-updated (story 13). Fetches are batched via paginated GraphQL, not per-repo calls (story 14).

**Blocked by:** 01.

**Status:** done

- [x] `ghstars.github` implements `ghstars.core`'s abstract client interface
- [x] `ghstars sync && ghstars list --json` returns real starred repos from the authenticated user's account
- [x] `Star` records are populated with the full field set, including `language`, `stargazer_count`, `fork`, `follow` — not just name/URL
- [x] `fork` is sourced from `viewer.repositories(affiliations:[OWNER])`, `follow` from `viewer.following`
- [x] Rate-limit check runs before fetch begins and prevents a stuck half-updated sync
- [x] Fetches use paginated GraphQL batching, no per-repo API calls

## Comments

Implemented in commit `f7d1545`. Live verification confirmed Star, fork,
and followed-owner fetches against GraphQL output.

`fetch_lists`/`create_list`/`update_list`/`delete_list`/`update_list_membership_for_item`/
`remove_star` raise `NotImplementedError` — deliberately out of scope, owned by
tickets 03/04/06.

`/code-review` flagged: `sync_cmd` not catching `GitHubApiError` (raw traceback
instead of clean hard-fail — fixed, verified with an unauthenticated-gh
reproduction); unguarded `json.loads` and no subprocess timeout (fixed);
an invalid pagination state when `hasNextPage` has no cursor (fixed);
duplicated pagination loops (consolidated); a stale docstring; and an unused
`isFork` field. Parallel fetches remain out of scope because they add
subprocess complexity without a required performance target.
