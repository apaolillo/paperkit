# Changelog

All notable changes to paperkit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

First public release.

### Added

- `paperkit build`: LaTeX builds with pdflatex, lualatex or xelatex and
  bibtex or biber, in a Docker image composed from `.paperkit.toml` (via
  pythainer) or on the host. Several build targets per project, built in
  parallel, or selected by name.
- `[texlive] source = "upstream"`: install TeX Live from a dated tlnet
  snapshot (or a closed release's final repository) so every image rebuild
  gets the same package set, optionally pinned by the snapshot's package
  database checksum.
- `paperkit check`: pre-submission checks on the build output, run in the
  image by default: LaTeX and bibliography log errors, overfull boxes, font
  embedding and Type 3 fonts, non-ASCII characters, trailing whitespace,
  final newlines, unused bibliography entries (per bib file, across every
  target using it), bibtex-tidy, and the toolchain that built the PDF.
- Page counts and limits: total pages and pages before references and
  acknowledgments, checked against `[page_limits]`. Both sections are exempt
  by default; `ack_counts_as_content = true` counts the acknowledgments as
  content, as at venues that exempt only the references.
- `paperkit bibtidy`: run bibtex-tidy on the bibliography in place.
  `--sort` / `--no-sort` chooses whether entries and fields are reordered;
  `[checks] bibtex_tidy.sort` sets the default for the command and the
  tidiness check alike. `paperkit tidy` still works as a hidden alias.
- Byte-reproducible builds: every engine, bibtex and biber run is pinned to
  one timestamp (`SOURCE_DATE_EPOCH` and `FORCE_SOURCE_DATE`, forwarded into
  the container), which fixes the PDF dates and font subset tags, and the
  trailer id is pinned too where the toolchain does not derive it from that
  timestamp. `[build] source_date_epoch` takes an epoch, an ISO date, or
  "git" (default: HEAD's committer date), and the report shows the timestamp
  used. The submission archive is pinned to the same timestamp, so the same
  sources zip to the same bytes from a fresh clone.
- `paperkit zip`: submission archive with configurable include and exclude
  patterns. `[zip] include_bbl` (or `--bbl`) also ships each main's compiled
  bibliography next to its .tex, for publishers that compile the sources
  without running BibTeX; it refuses to build an archive whose .bbl is
  missing and warns when one is older than its sources.
- Plain-text title and abstract exported next to each PDF, for pasting into
  submission forms. `\input`/`\include` files are resolved in Python, so no
  latexpand is needed, and a skipped export says why instead of staying
  silent.
- `paperkit shell`, and `base` and `acm` profiles.
- `paperkit init` pins a dated TeX Live snapshot that the release was tested
  against, so a new project is reproducible and `minted` works out of the box;
  `--texlive distro` keeps the base image's packages. `paperkit texlive-update`
  moves a project to the newest published snapshot (`--check` to only report),
  and is the only command that uses the network.
