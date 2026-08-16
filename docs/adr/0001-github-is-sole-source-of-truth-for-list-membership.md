# GitHub is the sole source of truth for List existence and membership

ghstars needed a rule for what happens when a Star's List membership changes both on GitHub (e.g. from phone/web) and locally since the last sync. We considered auto-merging the two (union), but decided GitHub always wins unconditionally — a conflicting local edit is never applied; it moves to a local-only Retriage Queue for the user to re-decide, and is never written to GitHub.

This also settled where that Retriage Queue itself lives: not a GitHub List. Putting conflict-handling state on GitHub would make GitHub responsible for a concept it doesn't natively have (a "pending conflict" marker), reintroducing the two-places-of-truth problem this decision exists to avoid, plus extra API cost, public-exposure risk, and orphaned state if ghstars is uninstalled. The Retriage Queue stays local, alongside the sync log — the same layer as everything else GitHub's `UserList` schema can't represent.
