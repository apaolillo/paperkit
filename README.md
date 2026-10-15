# paperkit

Reproducible builds and pre-submission checks for research papers. paperkit
builds your paper in a container composed from a config file, then checks it
for the problems that get submissions desk-rejected or camera-ready PDFs
bounced: page limits, Type 3 or unembedded fonts, LaTeX errors, overfull
boxes, unused bibliography entries. It currently supports LaTeX; Typst is on
the [roadmap](ROADMAP.md).

## Features

- **Container builds**: reproducible builds in Docker via
  [pythainer](https://github.com/apaolillo/pythainer), with every engine
  (pdflatex, lualatex, xelatex) and bibliography tool (bibtex, biber)
  installed, or builds on the host.
- **Pinned TeX Live**: optionally install TeX Live from a dated snapshot, so
  every image rebuild gets the same package set.
- **Page limits**: report total pages and pages before references and
  acknowledgments, and flag a paper over its configured limits.
- **Pre-submission checks**: LaTeX and bibliography log errors, overfull
  boxes, font embedding and Type 3 fonts, non-ASCII characters, trailing
  whitespace, final newlines, unused bibliography entries, bibtex-tidy.
- **Several targets per project**: build a paper and its companion documents
  in parallel, or just one of them; bibliography checks look at every target
  sharing a bib file.
- **Submission plumbing**: a source archive with configurable include and
  exclude patterns, and the title and abstract exported as plain text for
  pasting into submission forms.
- **Profiles**: defaults per publisher (base and ACM so far).

## Installation

Requires Python 3.13+ and, for container builds, Docker.

```bash
pip install paperkit
# or, as an isolated command-line tool:
uv tool install paperkit
```

## Quick start

```bash
# Generate a config file
paperkit init

# Build the paper (in Docker by default)
paperkit build

# Build on host (no Docker)
paperkit build --no-docker

# Run checks only (on existing build output, in Docker by default)
paperkit check

# Tidy the bibliography (add --no-sort to keep the entry order)
paperkit bibtidy

# Create submission archive
paperkit zip
```

## Configuration

paperkit looks for `.paperkit.toml` in the current directory or any parent. Example:

```toml
[project]
main = "paper"
content_dirs = ["content"]
bib = "references.bib"

[build]
engine = "pdflatex"         # pdflatex | lualatex | xelatex
passes = 3                  # 4th pass enables pbalance
shell_escape = true
bibtex = true               # use bibtex after pass 1
biber = false               # use biber instead of bibtex
output_dir = "out"
source_date_epoch = "git"   # timestamp builds are pinned to; see below

[docker]
base_image = "ubuntu:26.04"
image_name = "paper-builder"
extra_packages = []         # additional APT packages

[checks]
non_ascii = true
trailing_whitespace = true
final_newline = true
unused_bib = true
font_embedding = true       # requires poppler-utils
no_type3 = true             # warn on Type 3 (bitmap) fonts (part of font_embedding)
                            # full listing + Type 3 pages: out/<main>/fonts.txt
overfull_boxes = true
bibtex_tidy = { enabled = true, version = "1.14.0", sort = true }

[page_limits]                    # optional; without it the pages are only reported
total = 14                       # max pages, references included
before_refs = 14                 # max pages of content before the references
before_ack = 13                  # max pages of content before the acknowledgments
ack_counts_as_content = false    # see below

[zip]
name = "paper"
include = [
    "{main}.tex",
    "content/*.tex",
    "content/references.bib",
]
exclude = ["*.aux", "*.log", "*.out", "*.blg", "*.bbl"]
include_bbl = false         # also ship each main's compiled bibliography

[profile]
name = "base"               # base | acm
```

## Commands

| Command | Description |
|---|---|
| `paperkit build [NAMES]` | Build the paper PDFs (Docker by default) |
| `paperkit build --no-docker` | Build directly on the host |
| `paperkit shell` | Open an interactive shell in the Docker container |
| `paperkit check [NAMES]` | Run checks on existing build output (Docker by default) |
| `paperkit check --no-docker` | Run checks with the host's tools |
| `paperkit bibtidy` | Run bibtex-tidy on the bib file (in-place); `--no-sort` keeps the entry and field order |
| `paperkit zip` | Create submission archive; `--bbl` adds the compiled bibliographies |
| `paperkit init` | Generate a `.paperkit.toml` template |

Global options: `--config PATH` (config file), `-v/--verbose` (show Docker commands).

## Checks

| Check | What it does |
|---|---|
| LaTeX log | Parse `.log` for errors and warnings |
| BibTeX/Biber log | Parse `.blg` for errors and warnings |
| Boxes | Count overfull and underfull boxes |
| Toolchain | With `[texlive] source = "upstream"`: warn if the log shows the PDF was built with another TeX Live (e.g. the host's, via `--no-docker`) |
| Fonts | Verify all fonts are embedded (`pdffonts`) |
| Non-ASCII | Flag non-ASCII characters in `.tex` source |
| Trailing whitespace | Detect lines with trailing spaces |
| Final newline | Ensure each file ends with exactly one `\n` |
| Unused bib entries | Find bib entries no target cites, once per bib file (see below) |
| BibTeX tidy | Check bibliography formatting with bibtex-tidy (the same arguments `paperkit bibtidy` would apply) |

**Unused bib entries across targets.** With several mains sharing a bib file,
an entry is unused only if no target using that file cites it. paperkit reads
which bib files each target uses and what it cites from the target's `.aux`
(`\bibdata`, `\citation`, including `\@input` files and `\nocite{*}`) or, with
biber, its `.bcf`; no configuration is needed. With several targets, the
result is printed once per bib file in a "Bibliography" block.

When only some targets are built or checked (`paperkit build paper`), the
others are taken from their existing `.aux` if it is newer than their sources,
else from one draft LaTeX pass into a scratch directory (no PDF; the real
output is untouched). If that is disabled or fails, entries not cited by the
checked targets are listed as "other targets not checked", never as unused.

```toml
[checks.unused_bib]      # or simply: unused_bib = true | false
ignore = ["some_key"]    # never reported as unused (e.g. staged for later)
draft_pass = true        # resolve other targets with a draft pass when needed
```

**Page limits.** `[page_limits]` reports the total pages and the pages of
content before the references and the acknowledgments, and flags a paper over
its limits. A section starting mid-page counts that page. The sections are
found by their headings, so nothing has to be marked up in the source.

By default the acknowledgments and the references are both exempt: the
counted content ends at whichever comes first. Many venues (most ACM and
USENIX calls, for instance) exempt only the references and count
acknowledgments as text. Set `ack_counts_as_content = true` for those, and the
budget ends at the references heading instead:

```toml
[page_limits]
before_refs = 14
ack_counts_as_content = true   # acks sit inside the 14 pages
```

A check whose tool is missing (e.g. `pdffonts`, `bibtex-tidy`) is reported as
**skipped** (yellow) and makes the verdict "OK with warnings", so it never
passes silently. `paperkit check` runs in the Docker image by default, where
all tools are installed; `--no-docker` uses the host's. The TeX Live line of
the report comes from the build log, i.e. it names the engine that produced
the PDF, wherever the report is generated.

**Shipping the compiled bibliography.** Publishers often compile a submission
without running BibTeX, and ask for the `.bbl` alongside the sources (Springer's
LNCS checklist, for instance). `include_bbl = true`, or `paperkit zip --bbl`,
copies each included main's `<main>.bbl` out of the build directory and stores
it next to its `.tex` in the archive, which is where a publisher looks for it.
Build first: if a `.bbl` is missing the command stops and says so rather than
shipping an archive that cannot be compiled, and if a `.bbl` is older than its
`.tex` or the bib file, it warns that the archive may not match the sources.

## Profiles

**`base`**: sensible defaults for any paper. With `sort = false` the two
reordering arguments (`--sort=key`, `--sort-fields`) are dropped and the rest
still applies. Default bibtex-tidy args: `--curly --blank-lines --sort=key --duplicates=key,doi,citation --sort-fields --trailing-commas --remove-empty-fields --enclosing-braces=title --align=13`.

**`acm`**: for ACM conferences and journals. Currently identical to base; reserved for future ACM-specific defaults.

## Docker

The Docker image includes all engines and tools regardless of the current config, so switching between pdflatex/lualatex or bibtex/biber requires no rebuild.

Pre-installed: TeX Live (all major collections + luatex + xetex), biber, pygments, poppler-utils, npm, bibtex-tidy.

### Reproducible builds

Two builds of the same sources differ in three places, all written by the PDF
writer: the creation and modification dates, the random tags of subsetted
fonts (`VHDZTM+Calibri` one run, `EJHWCU+Calibri` the next), and the trailer
`/ID`. paperkit pins all three, so rebuilding gives byte-identical output.

Every engine, bibtex and biber run gets `SOURCE_DATE_EPOCH` and
`FORCE_SOURCE_DATE`, on the host and inside the container alike. The
timestamp comes from `[build] source_date_epoch`:

| Value | Meaning |
|---|---|
| `"git"` (default) | the committer date of HEAD |
| an integer | that epoch |
| an ISO date or date-time | that moment (dates are UTC midnight) |

A `SOURCE_DATE_EPOCH` already set in your environment wins over the config.
Outside a git repository, or before the first commit, paperkit warns that the
build is not reproducible and uses the current time. The report prints the
timestamp it used, so you can tell what a given PDF was built with:

```
Source date  1789898400 (2026-09-20 10:00:00 UTC, from git)
```

The trailer `/ID` needs help on older toolchains: from TeX Live 2024 on,
xdvipdfmx derives it from the epoch, but earlier versions do not, so paperkit
pins it from the epoch and the main's name (each main of a project gets its
own). Your sources are untouched: the definition is passed on the engine's
command line.

### TeX Live from a dated snapshot

By default TeX Live comes from the base image's `texlive-*` packages, so its
version is whatever the distribution ships, and it changes (or disappears) as
the distribution moves on. With `source = "upstream"`, paperkit instead runs
the official `install-tl` against a tlnet repository. Pointing it at a dated
snapshot gives the same TeX Live package set on every image rebuild:

```toml
[texlive]
source = "upstream"            # "distro" (default) | "upstream"
snapshot = "2026-09-18"        # dated snapshot from texlive.info
tlpdb_sha512 = "bcd7c792..."   # optional: pin the snapshot's package database
scheme = "small"               # install-tl scheme (without "scheme-")
collections = [                # added on top of the scheme (without "collection-")
    "latexextra", "fontsrecommended", "fontsextra", "publishers",
    "mathscience", "pictures", "bibtexextra",
]
packages = []                  # extra individual packages (installed with tlmgr)
docs = false                   # install documentation files
sources = false                # install source files
```

Repository selection, highest precedence first:

| Key | Repository |
|---|---|
| `repository = "https://..."` | Any tlnet URL, e.g. a private mirror |
| `snapshot = "YYYY-MM-DD"` | `https://www.texlive.info/tlnet-archive/YYYY/MM/DD/tlnet` |
| `year = 2025` | Frozen final repository of a closed release, from the TUG historic archive |
| none | Live CTAN mirror: current packages, **not reproducible** (paperkit warns) |

`snapshot` and `year` are mutually exclusive. Collection names are TeX Live's,
not Debian's: Debian's `texlive-science` is `mathscience`, and
`texlive-latex-extra` is `latexextra`.

TeX Live is installed under `/opt/texlive` (added to `PATH`), `tlmgr` is left
pointing at the same repository so later `tlmgr install` calls cannot pull
newer packages, and no distro `texlive-*` packages are installed. The TeX Live
layer comes before paperkit's tools, so it only rebuilds when `[texlive]` or
the base image changes. `minted` works out of the box: TeX Live ships
`latexminted` with its Python dependencies, and only a system `python3` is
needed. This is the recommended setup on `ubuntu:26.04`, whose distro
`minted` and `latexminted` versions do not work together.

**What is pinned.** The snapshot fixes the TeX Live package set: install-tl
checks every downloaded package against the snapshot's package database
(`tlpkg/texlive.tlpdb`), and `tlpdb_sha512` fixes that database itself. The
image build fails before downloading anything if the snapshot's database
changed. To get the value:

```bash
curl -fsSL https://www.texlive.info/tlnet-archive/YYYY/MM/DD/tlnet/tlpkg/texlive.tlpdb.sha512
```

The base image is not pinned by the snapshot. It hardly matters once TeX comes
from the snapshot (it only provides perl, python3 and paperkit's tools), but it
can be pinned by digest:

```toml
[docker]
base_image = "ubuntu:26.04@sha256:<digest>"
```

(`docker pull ubuntu:26.04 && docker image inspect --format '{{index .RepoDigests 0}}' ubuntu:26.04`
prints it.)

**Availability.** texlive.info is a single volunteer-run host. If it becomes
unavailable, use `year = ...` for a closed release (the TUG historic archive is
mirrored), or keep a copy of the snapshot on your own server and set
`repository`.

**Bumping.** Change `snapshot`, update `tlpdb_sha512` (command above), rebuild,
and diff the output PDF against the previous build.

## Development

Development uses [uv](https://docs.astral.sh/uv/); `uv.lock` pins the
development tools, so everyone formats and lints with the same versions.

```bash
uv sync                      # create .venv with paperkit and the dev tools
./scripts/all_checks.sh      # headers, format, lint, types, tests (all below)

uv run isort src tests       # formatting
uv run black src tests
uv run ruff check src tests  # linting
uv run mypy src              # type checking
uv run pytest                # tests
```

Releases follow [RELEASING.md](RELEASING.md); changes are listed in
[CHANGELOG.md](CHANGELOG.md).
