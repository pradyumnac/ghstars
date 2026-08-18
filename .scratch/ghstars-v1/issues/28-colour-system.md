# 28 — Colour system for Lists and Categories

**What to build:** List and Category names rendered in colour so groups are distinguishable at a glance. Default: colour hash-derived from the Category name, soft pastel, legible against both a light and a dark terminal background. The palette is overridable per Category in `tui.toml`. Spec stories 60-61.

**Blocked by:** 21 (the palette lives in config).

**Status:** ready-for-agent

- [ ] Every Category gets a deterministic default colour with no config present
- [ ] The same Category always gets the same colour within a session and across relaunches
- [ ] Default colours are checked for legibility against both a light and a dark Textual theme, not picked by eye on one terminal
- [ ] `tui.toml` can override the colour for a named Category; an override is used in place of the hash default
- [ ] A List with no Category (a General List) gets one fixed neutral colour, not a hash of an empty string
