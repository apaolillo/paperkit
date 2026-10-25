# The IEEE example

A conference paper in IEEEtran, under the `ieee` profile. It is the shape of
a paper bound for IEEE PDF eXpress: fonts checked after every build, the
whole PDF capped at the call's page count, and the compiled bibliography in
the archive.

```
paper.tex          the paper: author block, keywords, and the sections by name
content/           abstract, sections, acknowledgment
references.bib     the bibliography
.paperkit.toml     how it is built and what it must satisfy
```

## Try it

```bash
paperkit build                # in Docker; the first run builds the image
paperkit build --no-docker    # with the TeX Live installed on this machine
paperkit zip                  # paper-sources.zip, with paper.bbl next to paper.tex
```

## What it shows

- **The font check.** PDF eXpress rejects a PDF with a font that is not
  embedded or a Type 3 font. paperkit runs `pdffonts` on every build, lists
  each font with its type and embedding, and warns on a Type 3 one with the
  file it belongs to, so a plot saved as bitmaps is found before upload.
- **A cap on the whole PDF.** IEEE calls count references in the limit, so
  the file sets `total = 8` rather than `before_refs`.
- **A heading without a table-of-contents entry.** IEEEtran's
  `\section*{Acknowledgment}` writes nothing to the `.aux`, so paperkit
  finds the heading in the PDF text instead and still reports the pages
  before it.
- **What the profile adds.** `ieee` puts `IEEEtran.cls`, `IEEEtran.bst` and
  the `.bbl` in the archive, for PDF eXpress to compile without BibTeX. The
  file writes `include_bbl` out so the behaviour is visible without knowing
  the profile.

## Making it yours

Copy the directory, rename `paper.tex` and `[project] main`, replace the
sections, and set `total` to the call's number. `paperkit init --profile
ieee` writes a configuration like this one into an existing project.
