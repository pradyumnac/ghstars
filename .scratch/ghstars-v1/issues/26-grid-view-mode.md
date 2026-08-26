# 26 — Grid view mode

**Status:** retired

## Decision

Do not implement the grid card view. It depends on the retired Folder View Mode
switcher from ticket 25. The flat Star table and Layout presets meet the current
presentation needs.

Remove `grid_card_truncation` from `tui.toml`. No grid consumer exists for this
field.
