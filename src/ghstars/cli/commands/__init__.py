"""Every `ghstars` command, split by feature (ticket 19) instead of one
532-line `cli/__init__.py`. Each module here registers its command(s) on
the shared `app`/`category_app` Typer instances built in `ghstars.cli` via
`@app.command(...)`/`@category_app.command(...)`, the same decorators the
original single-file module used -- this package only changes where that
code lives, not how it behaves.

Importing this package (from `ghstars.cli`, after `app`/`category_app`
exist) is what actually runs those decorators; every import below is for
that side effect only.
"""

from ghstars.cli.commands import (  # noqa: F401
    category,
    diff,
    export,
    facets,
    list_lists,
    ratelimit,
    retriage,
    status,
    sync,
    tag,
    tui,
    unstar,
)
