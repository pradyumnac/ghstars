# 04 — Local tagging & two-way sync push

**What to build:** `ghstars tag` changes a Star's List membership locally; sync pushes the change to GitHub via `updateUserListsForItem`. That mutation replaces a Star's *entire* list membership per call — the sync engine must always compute and send the complete desired `listIds` set, never a delta. Writes are idempotent where feasible, so retrying after a timeout doesn't manufacture a spurious conflict against your own prior attempt (story 32). New Lists created as a side effect of tagging default to public, matching the account's existing Lists, with an explicit `isPrivate` override available (story 48).

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] `ghstars tag <repo> <list>` changes membership locally
- [ ] Sync pushes the change via `updateUserListsForItem`, always sending the full desired `listIds` set, never a delta
- [ ] Retrying a timed-out write doesn't create a spurious conflict against the same prior attempt
- [ ] A List created by tagging defaults to public unless `--private`/an explicit `isPrivate` override is given
- [ ] Phone/web view of Lists reflects local tagging changes after sync (story 7)
