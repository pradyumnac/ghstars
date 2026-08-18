# 25 — View mode switcher and Folder view

**What to build:** a key that cycles View Mode. Folder view: each List is shown as a container; opening one shows its Stars, one level deep — a Folder never holds another Folder. A Star that belongs to no List falls back to one default Folder. Flat list stays the default mode on launch, unchanged. Spec stories 50-52.

**Blocked by:** 21 (the mode-switch key must be overridable, per ticket 21's keybinding config).

**Status:** ready-for-agent

- [ ] A key cycles View Mode; flat list is the default on first launch
- [ ] Folder view lists every List as a container; opening one shows exactly that List's Stars
- [ ] A Star in zero Lists appears in one default Folder, reachable the same way as any other
- [ ] Opening a Folder never shows a second level of Folders inside it
