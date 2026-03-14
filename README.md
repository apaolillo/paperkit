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

# Run checks only (on existing build output)
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
| `paperkit check` | Run checks on existing build output |
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
| Fonts | Verify all fonts are embedded (`pdffonts`) |
| Non-ASCII | Flag non-ASCII characters in `.tex` source |
| Trailing whitespace | Detect lines with trailing spaces |
| Final newline | Ensure each file ends with exactly one `\n` |
| Unused bib entries | Find defined but uncited bibliography keys |
| BibTeX tidy | Check bibliography formatting with bibtex-tidy |

## Profiles

**`base`** — Sensible defaults for any LaTeX paper. Default bibtex-tidy args: `--curly --blank-lines --sort=key --duplicates=key,doi,citation --sort-fields --trailing-commas --remove-empty-fields --enclosing-braces=title --align=13`.

**`acm`** — For ACM conferences/journals. Currently identical to base; reserved for future ACM-specific defaults.

## Docker

The Docker image includes all engines and tools regardless of the current config, so switching between pdflatex/lualatex or bibtex/biber requires no rebuild.

Pre-installed: TeX Live (all major collections + luatex + xetex), biber, pygments, poppler-utils, npm, bibtex-tidy.

## Development

```bash
pip install -e '.[dev]'

black src/
isort src/
ruff check src/
mypy src/
```
