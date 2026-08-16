# 13 — Packaging & distribution (Linux)

**What to build:** ghstars installable via `uv tool install`, published to PyPI, with a Linux tar.gz binary on GitHub Releases via a GitHub Actions workflow (repo is public, so Actions is free/unlimited-minute regardless of runner OS — but Windows/macOS builds are deliberately deferred to ticket 15, not because of cost). Structured to accommodate future `pipx`/`uvx`/`mise`/`eget` install paths and the later Windows/macOS builds, without building either now.

**Blocked by:** 05, 06, 07, 08, 09, 10, 11, 12 — all v1-functional pieces must be in place before cutting a distributable release.

**Status:** ready-for-agent

- [ ] `uv tool install ghstars` works from a built package
- [ ] Package published to PyPI
- [ ] Linux tar.gz binary attached to a GitHub Release via a GitHub Actions release workflow
- [ ] Packaging layout doesn't foreclose adding `pipx`/`uvx`/`mise`/`eget` later, or the Windows/macOS builds in ticket 15
