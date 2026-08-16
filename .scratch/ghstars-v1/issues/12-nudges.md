# 12 — Nudges

**What to build:** The nudge store in `ghstars.core`: recording an observation about workflow friction (a stable slug/key, theme, message, count, last_seen) without ever acting on it. Nudges dedup by their stable key so repeated friction doesn't spam duplicate notes. Surfacing is off by default and, when enabled, only appears on human-facing surfaces — never in `--json`/agent-mode output, so the CLI's token-efficiency promise to agents holds. The agent skill only reads nudge files when it has something new to record, not on every call.

**Blocked by:** 08.

**Status:** ready-for-agent

- [ ] `ghstars.core` nudge store records slug/theme/message/count/last_seen under `runtime/nudges/<theme>.md`
- [ ] Recording a nudge with an existing slug increments/updates rather than duplicating
- [ ] Nudge surfacing is off by default
- [ ] Nudges never appear in `--json`/agent-mode output, regardless of the surfacing setting
- [ ] Nudge files are only read when there's something new to record, not on every invocation
