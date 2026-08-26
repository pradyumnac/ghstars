# 25 — View mode switcher and Folder view

**Status:** retired

## Decision

Do not implement Folder View Mode. The flat Star table already supports Filter,
Search, Sort, membership-chip filtering, and the Unclassified queue. These
flows cover the triage use case without hierarchical navigation.

The TUI has Layout presets, not View Modes. A Layout changes table columns,
row height, and Detail pane settings. It does not change the Star arrangement.

## Downstream effect

- Ticket 26 is retired because its grid depends on the View Mode switcher.
- Ticket 27 no longer needs Filter-within-Folder behavior.
- Remove the unused `view_mode` state field.
