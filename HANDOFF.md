# Handoff

Use this file only for context that has no better home. Ticket files contain
acceptance criteria and implementation notes. The spec and ADR index contain
design decisions. Remove notes after they move to those sources.

## Task rail

The harness Task list is authoritative during a session. Keep this section as
an empty-or-current summary when work continues across sessions.

## Resume notes

- Check `.scratch/ghstars-v1/issues/` for ticket status and comments.
- Read `.scratch/ghstars-v1/spec.md` for stories 50-72.
- Read `docs/adr/INDEX.md` before changing architecture.
- Ticket 27 is partial. Flat-view filters, search, sorting, license display,
  persistence, and explicit sync are implemented. Folder integration waits
  for ticket 25. See issue 27 for details.
- The next unblocked tickets are 12, 23, 24, 25, and 28. Ticket 26 waits for
  ticket 25.
- Story 47 has no ticket. Create one after ticket 14 defines the retirement
  mechanism for `gh-stars.py` and `github-stars`.

## Pending investigation

- The Star-list selection mark can disappear in a real terminal after the
  select key is pressed. Headless tests pass. Reproduce this in `ghstars tui`
  before changing code or creating a ticket.

## Safety

- Do not run `sync` against the user's account without explicit permission.
- Do not run real unstar or List mutations during development or tests.
- For approved sync tests, use an isolated state directory and keep the normal
  GitHub authentication configuration separate. See ADR 0002 and the sync
  command for the storage paths.
- The test List `zzz-ghstars-verify-delete-me` still exists on the account.
  Do not delete it through development code.

## Development checks

- Use a worktree for ticket-scoped changes when parallel work is active.
- Run the ticket tests, the full test suite, and diagnostics before handoff.
- Update the ticket file and this note only when the information is not
  already recorded in the spec, an ADR, or project documentation.
