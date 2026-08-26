# 13 — Packaging & distribution (Linux)

**What to build:** ghstars installable via `uv tool install`, published to PyPI, with a Linux tar.gz binary on GitHub Releases via a GitHub Actions workflow (repo is public, so Actions is free/unlimited-minute regardless of runner OS — but Windows/macOS builds are deliberately deferred to ticket 15, not because of cost). Structured to accommodate future `pipx`/`uvx`/`mise`/`eget` install paths and the later Windows/macOS builds, without building either now.

**Blocked by:** 05, 06, 07, 08, 09, 10, 11, 12, 14 — all v1-functional pieces must be in place before cutting a distributable release.

**Status:** ready-for-agent

- [ ] `uv tool install ghstars` works from a built package
- [ ] Package published to PyPI
- [ ] Linux tar.gz binary attached to a GitHub Release via a GitHub Actions release workflow
- [ ] Packaging layout doesn't foreclose adding `pipx`/`uvx`/`mise`/`eget` later, or the Windows/macOS builds in ticket 15
- [ ] `tests/test_packaging.py` no longer breaks a plain `pytest` run

## Comments

**2026-08-26, from a review of commit 59bf8f8.**
`tests/test_packaging.py:8-16` runs `uv build` in a subprocess. The `uv`
executable is not a declared dependency. `pyproject.toml:23` names
`uv_build` only, which is the build backend, not the command-line tool.

A plain `pytest` run therefore fails on a machine that has every Python
dependency but no `uv`.

Fix this when you build this ticket. Mark the test and deselect it from
the default run, then run it from the `mise` build task. A `shutil.which`
guard with `pytest.skip` also works, but a packaging check that skips
itself can rot without anyone noticing.
