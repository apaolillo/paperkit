# paperkit

Reusable build toolkit for LaTeX papers. Build, check, tidy, and archive (locally or in Docker).

## Features

- **Multi-engine builds** — pdflatex, lualatex, xelatex with bibtex or biber
- **Docker builds** — reproducible containerized builds via [pythainer](https://github.com/open-s4c/pythainer), all engines and tools pre-installed
- **9 automated checks** — log errors, overfull boxes, font embedding, non-ASCII, trailing whitespace, final newline, unused bib entries, bibtex-tidy
- **Colored report** — summary table with status icons and overall verdict
- **Bibliography tidying** — run bibtex-tidy in-place with profile-specific args
- **Submission archive** — create a zip with configurable include/exclude patterns
- **Profile system** — base and ACM profiles for project-type defaults

## Installation

Requires Python 3.13+.

```bash
pip install -e .
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

# Tidy the bibliography
paperkit tidy

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

[docker]
base_image = "ubuntu:25.04"
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
bibtex_tidy = { enabled = true, version = "1.14.0" }

[zip]
name = "paper"
include = [
    "{main}.tex",
    "content/*.tex",
    "content/references.bib",
]
exclude = ["*.aux", "*.log", "*.out", "*.blg", "*.bbl"]

[profile]
name = "base"               # base | acm
```

## Commands

| Command | Description |
|---|---|
| `paperkit build` | Build the paper PDF (Docker by default) |
| `paperkit build --no-docker` | Build directly on the host |
| `paperkit build --shell` | Open interactive shell in the Docker container |
| `paperkit check [NAMES]` | Run checks on existing build output (Docker by default) |
| `paperkit check --no-docker` | Run checks with the host's tools |
| `paperkit tidy` | Run bibtex-tidy on the bib file (in-place) |
| `paperkit zip` | Create submission archive |
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
| Unused bib entries | Find defined but uncited bibliography keys |
| BibTeX tidy | Check bibliography formatting with bibtex-tidy |

A check whose tool is missing (e.g. `pdffonts`, `bibtex-tidy`) is reported as
**skipped** (yellow) and makes the verdict "OK with warnings", so it never
passes silently. `paperkit check` runs in the Docker image by default, where
all tools are installed; `--no-docker` uses the host's. The TeX Live line of
the report comes from the build log, i.e. it names the engine that produced
the PDF, wherever the report is generated.

## Profiles

**`base`** — Sensible defaults for any LaTeX paper. Default bibtex-tidy args: `--curly --blank-lines --sort=key --duplicates=key,doi,citation --sort-fields --trailing-commas --remove-empty-fields --enclosing-braces=title --align=13`.

**`acm`** — For ACM conferences/journals. Currently identical to base; reserved for future ACM-specific defaults.

## Docker

The Docker image includes all engines and tools regardless of the current config, so switching between pdflatex/lualatex or bibtex/biber requires no rebuild.

Pre-installed: TeX Live (all major collections + luatex + xetex), biber, pygments, poppler-utils, npm, bibtex-tidy.

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
needed.

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

```bash
pip install -e '.[dev]'

black src/
isort src/
ruff check src/
mypy src/
pytest
```
