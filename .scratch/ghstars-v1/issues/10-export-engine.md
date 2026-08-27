# 10 — Export engine

**Amended by ticket 32:** the config location described below
(`get_export_config_path()`, `~/.ghstars/config/export.toml`) moved.
Export config now lives in the `[export]` table of
`~/.ghstars/config/ghstars.toml`, loaded by
`ghstars.core.config.load_core_config`. `ExportConfig`/`ExportEntry`
(the schema) and `select_stars`/`run_export` (selection and writing)
are unchanged — see ticket 32 for the rest of the three-tier config
split.

**What to build:** A generic, config-driven export engine mapping a List (or Category) to an output file and format, so the user can drive their own downstream pipelines (`tools.yaml`, skill vendor lists) without ghstars hardcoding specific use cases. No hardcoded exporters — `tools.yaml`/`tools-under-exploration.yaml`-shaped mappings ship as example config, not special-cased code paths. Supports the "what am I currently exploring but haven't tried yet" query (story 35) as a config-driven case, not a bespoke command.

**Blocked by:** 03.

**Status:** done

- [x] Export mapping (List/Category → output file + format) is read from config, not hardcoded
- [x] `ghstars export` produces output matching an example `tools.yaml`-shaped mapping
- [x] The "Explore, not yet tried" query is answerable via a config-driven mapping, no special-cased command
- [x] Export skips and reports a malformed List rather than exporting it under a guessed Intent/Category

## Comments

Implemented `ghstars.core.export` (new module) plus a `ghstars export`
CLI command (`src/ghstars/cli/__init__.py`, `get_export_config_path()`
added to `cli/deps.py`). Config lives at
`~/.ghstars/config/export.toml`, read via stdlib `tomllib` (per ADR
0002: `config/` is TOML/YAML, plain-text, git-diffable -- no new
dependency needed for the read side).

Each `[[exports]]` entry selects Stars either by exact List name
(`list_name`) or by Category with an optional Intent filter
(`category` + `intent`), and writes them to `output` in `format`
(`yaml`/`json`/`csv`). The Category+Intent form is how "what am I
exploring but haven't tried yet" (story 35) is answered generically --
`category = "..."`, `intent = "Explore"` -- one config entry, no
special-cased command. Example config, matching the ticket's
`tools.yaml`/`tools-under-exploration.yaml` shape, is documented in
`docs/how-to/export.md` rather than shipped as code.

**Field named `list_name`, not `list`:** a field literally named `list`
on the same Pydantic model as `fields: list[str] | None` shadows the
builtin `list` type during Python 3.14's lazy annotation evaluation
(PEP 649) -- pydantic evaluates `list[str]` against a namespace where
`list` already resolves to the field itself, not the builtin, and
model construction breaks with a bare `TypeError`. Caught by running
`mise run check` locally (the failure showed up immediately at
collection time); worth flagging for future tickets on this same
Python version, since it will keep surprising anyone who reaches for
`list` as a field name near another field typed `list[...]`.

**Malformed-List handling (last acceptance criterion):** a malformed
List's `intent`/`category` are always `None` post-`classify_list()`
(ticket 03), so neither selector can ever match one on the merits --
that half is a natural consequence of ticket 03's existing design, not
new logic here. What ticket 17 actually flagged as a risk is a
*naive* implementation guessing from the raw, unparsed name. Added
`_looks_related()`: if a malformed List's raw `name` textually
contains the entry's `list_name`/`category` (case-insensitive), it's
reported in `ExportEntryResult.skipped_malformed_lists` and surfaced
as a `ghstars export` warning, naming the List, but never exported
under a guessed classification. Covered by
`test_select_stars_reports_a_related_malformed_list_as_skipped` /
`test_select_stars_does_not_report_an_unrelated_malformed_list` in
`tests/test_export.py`, plus a CLI-level warning test in
`tests/test_cli.py`.

Added `pyyaml` as a new runtime dependency (`yaml.safe_dump` only, for
the `yaml` output format -- ghstars never parses YAML, so the
historical `yaml.load`-on-untrusted-input CVE class doesn't apply).
Ran the `dependency-review` skill first per the user's global
`AGENTS.md`: MIT-licensed, long-maintained, narrow footprint for this
write-only use, no applicable CVEs found for the `safe_dump` path.

**`/code-review` findings, both fixed:**
- A `~`-prefixed `output` (e.g. `~/repos/dotfiles/tools.yaml`, the
  exact dotfiles-repo use case this ticket targets) was not expanded,
  so it silently wrote under a literal `./~/...` directory instead of
  the home directory. Fixed with `Path.expanduser()` before the
  `is_absolute()` check; regression-tested
  (`test_run_export_expands_a_tilde_prefixed_output_to_the_home_dir`).
- `run_export` wrote output files with a plain `write_text`, not the
  temp-file+rename pattern `StateStore` already uses elsewhere in this
  codebase, so a killed process or a concurrent reader could see a
  truncated `tools.yaml`. Fixed by renaming `state_store.py`'s
  module-private `_atomic_write` to public `atomic_write` and reusing
  it here, rather than duplicating the logic; regression-tested
  (`test_run_export_leaves_no_temp_file_behind`).

Not flagged/not changed: nothing outstanding as a design question --
both review findings were code-quality fixes, applied directly.

Final `mise run check`: fmt/lint/typecheck/test all clean, 136 tests
passing (22 new in `tests/test_export.py`, 5 new in `tests/test_cli.py`).
