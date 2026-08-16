# 03 — Fetch Lists & parse taxonomy

**What to build:** Sync also pulls the user's existing GitHub Lists and their membership (`viewer.lists`), so classification already done on github.com is respected, not overwritten. List names parse into `Intent` (`Explore`/`Current`/`Retired`/`Reference`/`None` for General) and `Category` per the `{Intent}: {Category}` convention. Names that don't conform (e.g. an existing unprefixed "Vendored skills" list) are flagged as needing a rename rather than silently guessed at. Unclassified new stars land in `Explore: General` by default.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] Sync fetches `viewer.lists` (id, name, slug, description, isPrivate, items) alongside stars
- [ ] List names parse into Intent/Category; `Explore`/`Current`/`Retired`/`Reference` recognized, General (no prefix) recognized
- [ ] Malformed names are flagged for the user to resolve, never auto-assigned an Intent
- [ ] `ghstars list --json --fields intent,category` reflects parsed classification for real Lists
- [ ] New unclassified stars default to `Explore: General`
