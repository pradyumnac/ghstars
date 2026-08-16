# 15 — Windows & macOS release binaries

**What to build:** Extend the release workflow from ticket 13 to also build and attach Windows and macOS tar.gz (or platform-native archive) binaries to GitHub Releases, so distribution isn't Linux-only. Deliberately sequenced after 13 rather than bundled into it, so the first release isn't blocked on cross-platform build issues.

**Blocked by:** 13.

**Status:** ready-for-agent

- [ ] Windows binary built and attached to GitHub Releases
- [ ] macOS binary built and attached to GitHub Releases
- [ ] Release workflow runs all three platforms (Linux, Windows, macOS) on the same tag/release trigger
