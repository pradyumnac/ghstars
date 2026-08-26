# 12 — Nudges

**Status:** retired

## Decision

Do not build a Nudge store or write files under `runtime/nudges/`. Do not add
Nudge persistence, deduplication, or display settings.

Ticket 14 now requires the agent skill to tell the user about a relevant
workflow observation directly. The agent does not persist or apply the
observation.
