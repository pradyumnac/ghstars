# 10 — Export engine

**What to build:** A generic, config-driven export engine mapping a List (or Category) to an output file and format, so the user can drive their own downstream pipelines (`tools.yaml`, skill vendor lists) without ghstars hardcoding specific use cases. No hardcoded exporters — `tools.yaml`/`tools-under-exploration.yaml`-shaped mappings ship as example config, not special-cased code paths. Supports the "what am I currently exploring but haven't tried yet" query (story 35) as a config-driven case, not a bespoke command.

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] Export mapping (List/Category → output file + format) is read from config, not hardcoded
- [ ] `ghstars export` produces output matching an example `tools.yaml`-shaped mapping
- [ ] The "Explore, not yet tried" query is answerable via a config-driven mapping, no special-cased command
