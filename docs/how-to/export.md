# Export Stars to a file

`ghstars export` writes local Stars to file, in the format and location
you choose. Use it to feed a downstream tool: a `tools.yaml` for a
dotfiles pipeline, a vendor list for a skill, or any other flat file a
script of yours reads.

ghstars ships no built-in exporter for any one use case. You define each
export in config. The examples below are one way to configure it, not a
fixed feature.

> Export config used to live in its own `~/.ghstars/config/export.toml`.
> That file is retired — ghstars no longer reads it, and prints a
> one-time warning on stderr if it finds one on disk. Move its entries
> into the `[export]` table of `ghstars.toml`, then delete the old file.

## Configure an export

Create `~/.ghstars/config/ghstars.toml`. Add one `[[export.exports]]`
entry per output file — export config lives under the `[export]` table,
alongside every other core-tier setting (see the three-tier config ADR).

```toml
# Adopted skills the user actively uses, as tools.yaml.
[[export.exports]]
name = "tools"
list_name = "Current: Vendored Skills"
output = "tools.yaml"
format = "yaml"

# Candidate skills under evaluation, not yet adopted.
[[export.exports]]
name = "tools-under-exploration"
category = "Vendored Skills"
intent = "Explore"
output = "tools-under-exploration.yaml"
format = "yaml"
```

Run `ghstars export` from inside the repo where these files must land. A
relative `output` path resolves against the current directory. Give an
absolute path, or a path starting with `~`, to write to a fixed location
instead — e.g. `output = "~/repos/dotfiles/tools.yaml"`.

## Entry fields

Each `[[export.exports]]` entry takes these fields.

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | A label for this entry, used in `ghstars export`'s report. |
| `list_name` | one of `list_name`/`category` | The exact name of one List to export, e.g. `"Current: Vendored Skills"`. |
| `category` | one of `list_name`/`category` | A Category to export. Matches every List with this Category, across every Intent, unless you also set `intent`. |
| `intent` | no | Combine with `category` to match one Intent only, e.g. `"Explore"`. Not valid with `list_name`. |
| `output` | yes | The file path to write. |
| `format` | yes | `"yaml"`, `"json"`, or `"csv"`. |
| `fields` | no | Star fields to include, in order. Defaults to `full_name`, `html_url`, `description`. Run `ghstars list --fields` to see every available field. |

Set exactly one of `list_name` or `category` per entry. `ghstars export`
rejects a config file that sets both, or neither, on the same entry.

## Answer "what am I exploring but have not tried yet"

Use a `category` entry with `intent = "Explore"`, as in the second
example above. `Explore` is the Intent for a candidate you have not yet
adopted (see `CONTEXT.md`). No separate command exists for this — it is
one export entry, like any other.

## A malformed List is never guessed at

A List whose name only partly matches the `{Intent}: {Category}`
pattern is malformed (see `CONTEXT.md` and `ghstars lists --fields
malformed`). `ghstars export` never exports a malformed List under a
guessed Intent or Category.

If a malformed List's raw name looks related to one of your export
entries, `ghstars export` still skips it, and prints a warning that
names it. Rename the List on GitHub to match the `{Intent}: {Category}`
convention, then run `ghstars sync` again.
