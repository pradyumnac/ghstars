# 28 — TUI discovery layout, category cues, and status line

**What to build:** Improve the TUI layout for onboarding and categorising
existing Stars. The table starts with newest Stars. It helps users find
unclassified, Explore, Intent, Category, and List results. Colour is a secondary
Category cue. Use Textual semantic text roles. Do not add an application theme,
palette, or hard-coded colour set.

**Blocked by:** 21 (done).

**Status:** done

## Scope 1 — Category cues and accessibility

- [x] Keep the List name and Intent text visible. Colour must not be the only
      Category cue.
- [x] Map each Category to an approved Textual semantic text role. Use
      `$text-primary`, `$text-secondary`, `$text-accent`, or `$text-success`.
- [x] Use a stable digest of the Category string to select its default role. A
      collision is acceptable because the Category text remains visible.
- [x] Let `tui.toml` map a named Category to an approved semantic text role.
      Reject an unknown role with a clear configuration error.
- [x] Render General Lists with `$text-muted`. Do not hash an empty Category.
- [x] Do not add named themes, raw per-Category colour values, pastel
      generation, or new palette settings.
- [x] Render the cues in every TUI surface that shows a List or Category.
- [x] Test default selection, stable selection, General List rendering, valid
      overrides, invalid overrides, and visible text without colour.

## Scope 2 — Discovery layout

Start this scope after Scope 1 passes its tests.

- [x] Start with newest Stars on the first launch. Keep the existing saved
      filter and sort behavior for later launches.
- [x] Add a title row. Show compact API and sync icons on its right side. Do
      not use colour as the only API or sync cue.
- [x] Add a discovery row below the title. Align collection counts right.
- [x] Show `[ / ] Search`, `[ f ] Filter`, `[ s ] Sort`, and `[ x ] Clear` in
      the bottom status bar. Align them right and keep key hints compact.
- [x] Use subtle semantic text colours for key tokens and active search, Filter,
      and sort values. Keep brackets and text as colour-independent cues.
- [x] Show Stars, Lists, Unclassified, and Pending counts on the right.
- [x] Let the Unclassified count open the unclassified filter.
- [x] Render each List membership as a short Intent-and-Category chip.
- [x] Selecting a membership chip applies its Intent-and-Category filter.
- [x] In compact mode, show one-line rows with Star name, language, star count,
      and membership chips.
- [x] In balanced mode, keep one-line rows and show more table columns.
- [x] Store the user default layout in `config/tui.toml`. Store the last active
      layout in `state/tui-state.toml`.
- [x] Keep the bottom detail pane toggleable in both modes.
- [x] On narrow terminals, preserve Star name, language, and star count first.
      Hide membership chips and show a List count indicator instead.
- [x] Hide lower-priority columns and panes progressively. Do not add horizontal
      scrolling or a second compact layout.
- [x] Test compact and balanced modes, saved settings, chip filtering,
      unclassified filtering, and narrow terminal behavior.

## Scope 3 — Status updates

Start this scope after Scopes 1 and 2 pass their tests.

- [x] Replace the separate API rate, sync state, and result displays with the
      title row, discovery row, and bottom status bar from Scope 2.
- [x] Show API and Sync on the title row. Use compact icons and bracketed values.
      The initial values are `[◌ checking]` and `[↻ idle]`.
- [x] Show Stars, Lists, Unclassified, and Pending in bracketed sections on the
      right side of the discovery row.
- [x] Update the API section after a rate-limit refresh or failure.
- [x] Update the Sync section for every sync stage and completion or failure.
- [x] Update Stars, Lists, Unclassified, and Pending after local state reloads,
      filtering, tagging, unstar, and sync.
- [x] Do not duplicate visible/total count, active Filter, or active sort in
      another bar when ticket 24 adds them.
- [x] Replace tests for affected widgets. Add tests for initial placeholders and
      each update path.

## Design basis

WCAG 2.2 requires a cue other than colour when colour communicates information.
It requires 3:1 contrast for meaningful non-text cues. Textual semantic text
roles are legible against its background, surface, and panel colours. These rules
avoid a second theme system and raw colours that fail under a different active
theme.

Sources:

- <https://www.w3.org/WAI/WCAG22/Understanding/use-of-color>
- <https://www.w3.org/WAI/WCAG22/understanding/non-text-contrast.html>
- <https://textual.textualize.io/guide/design/>
- <https://www.nngroup.com/articles/visual-indicators-differentiators/>

## Comments

Implemented all three scopes. The TUI now uses semantic Category cues, focused
status rows, two saved density modes, and responsive columns. API, sync, and
collection updates use the top rows. Discovery controls use the bottom bar.

The bottom bar now places Search, Filter, Sort, and Clear on the left. Action
hints remain on the right. The title and status rows have consistent horizontal
insets. TUI tests and quality checks pass after this layout adjustment.

Verification:

- `uv run pytest`: 270 tests passed.
- `uv run ruff format --check .`: passed.
- `uv run ruff check .`: passed.
- `uv run mypy src tests`: passed.

**2026-08-26, two criteria overridden by ticket 23 and ADR 0008.**

Scope 1's Category colour rules change. `category_colours` no longer maps
a Category to a Textual semantic text role. It maps to a named colour
from a fixed set. Every colour in that set must reach 3:1 contrast on a
light background and on a dark background.

The rest of Scope 1 stands. Colour is never the only Category cue. The
Category text stays visible. A stable digest still picks the default.

Scope 2's narrow-terminal rules change. The table now keeps every
configured column and scrolls horizontally. Progressive column hiding,
the `_narrow` check, and its 90-column threshold are removed. The layout
preset and the user's toggle control the detail pane.

Scope 2's "Store the user default layout in `config/tui.toml`. Store the
last active layout in `state/tui-state.toml`" rule stands. ADR 0008
records why a preset definition and an active selection are two facts,
not one duplicated fact.

Scope 3 is unchanged.
