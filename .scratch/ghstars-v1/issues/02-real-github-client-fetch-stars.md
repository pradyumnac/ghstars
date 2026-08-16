# 02 — Real GitHub client: fetch stars

**What to build:** `ghstars.github`, the concrete client implementing `ghstars.core`'s abstract interface over `gh api graphql`, swapped into the CLI wiring from 01 in place of the fake. Fetches `viewer.starredRepositories` (paginated) for the base star list, plus `viewer.repositories(affiliations:[OWNER])` for fork status and `viewer.following` for follow status — both needed to populate the `Star` model's `fork`/`follow` fields, not just the obvious ones. A real rate-limit check runs before any fetch begins, so a large sync can't get stuck mid-way and leave state half-updated (story 13). Fetches are batched via paginated GraphQL, not per-repo calls (story 14).

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] `ghstars.github` implements `ghstars.core`'s abstract client interface
- [ ] `ghstars sync && ghstars list --json` returns real starred repos from the authenticated user's account
- [ ] `Star` records are populated with the full field set, including `language`, `stargazer_count`, `fork`, `follow` — not just name/URL
- [ ] `fork` is sourced from `viewer.repositories(affiliations:[OWNER])`, `follow` from `viewer.following`
- [ ] Rate-limit check runs before fetch begins and prevents a stuck half-updated sync
- [ ] Fetches use paginated GraphQL batching, no per-repo API calls
