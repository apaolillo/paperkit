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
  acknowledgments, checked against `[page_limits]`.
- `paperkit tidy`: run bibtex-tidy on the bibliography in place.
- `paperkit zip`: submission archive with configurable include and exclude
  patterns.
- Plain-text title and abstract exported next to each PDF, for pasting into
  submission forms.
- `paperkit shell` and `paperkit init`, and `base` and `acm` profiles.
