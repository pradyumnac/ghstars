"""Add a Category to the `[taxonomy]` vocabulary in `ghstars.toml`.

ghstars writes `config/` only at the user's explicit instruction -- never on
their behalf (ADR 0002, as amended by ADR 0005). `tomlkit` round-trips the
file, so comments and formatting survive: the config stays hand-editable and
git-diffable, which is the property ADR 0002 protects.
"""

from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError

from ghstars.core.state_store import atomic_write
from ghstars.core.taxonomy import blessed_categories, normalize_category


class BlessError(Exception):
    """`ghstars.toml` cannot take this Category."""


def bless_category(path: Path, category: str) -> str:
    """Append `category` to `[taxonomy] categories`, and return it normalized.

    Creates the file and the table when absent. Idempotent: a Category
    already blessed under any spelling is left alone.
    """
    normalized = normalize_category(category)
    if not normalized:
        raise BlessError(
            f"{category!r} normalizes to nothing: a Category cannot be empty, "
            "whitespace, or underscores only"
        )

    if path.exists():
        try:
            doc = tomlkit.parse(path.read_text())
        except TOMLKitError as exc:
            raise BlessError(f"{path}: invalid TOML: {exc}") from exc
    else:
        doc = tomlkit.document()

    table = doc.get("taxonomy")
    if table is None:
        table = tomlkit.table()
        doc["taxonomy"] = table

    existing = table.get("categories")
    if existing is None:
        # No table yet means the defaults were in force. Seed the explicit
        # list from them, so blessing one word does not silently drop the
        # other eleven.
        from ghstars.core.taxonomy import DEFAULT_CATEGORIES

        existing = tomlkit.array()
        existing.extend(sorted(DEFAULT_CATEGORIES))
        existing.multiline(True)
        table["categories"] = existing

    if normalized in blessed_categories(existing):
        return normalized

    existing.append(normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, tomlkit.dumps(doc))
    return normalized


__all__ = ["BlessError", "bless_category"]
