# 07 — Category rename & drain

**What to build:** `ghstars category rename` renames a Category and updates all its Lists across Intents (Explore/Current/Retired variants) consistently in one operation, instead of the user manually renaming each variant. `ghstars category drain` bulk-migrates every Star from one Category into another. Any List created as a side effect of either operation follows the same public-by-default-with-`isPrivate`-override rule as ticket 04.

**Blocked by:** 04, 05.

**Status:** ready-for-agent

- [ ] `ghstars category rename <old> <new>` renames all Intent-variant Lists for that Category consistently
- [ ] `ghstars category drain <from> <to>` bulk-migrates all Stars from one Category to another
- [ ] Lists created by rename/drain default to public unless an explicit `isPrivate` override is given
- [ ] Both commands respect List-name validation from 03 (no malformed names produced)
- [ ] `drain`/`rename` fetch fresh GitHub state before computing/writing the bulk change, and skip and report (never silently overwrite) any Star whose live List membership has already diverged from what triggered the migration
