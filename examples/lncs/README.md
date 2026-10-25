# The LNCS example

A paper in Springer's `llncs` class, under the `lncs` profile. It is the
shape of a paper bound for an LNCS volume: the whole PDF capped at the
volume's page count, the compiled bibliography in the archive as Springer's
checklist asks, and a bibliography shared with a future extended version.

```
paper.tex          the paper: title, authors, institutes, and the sections by name
content/           abstract, sections, acknowledgments
references.bib     the bibliography, with one entry the extended version cites
.paperkit.toml     how it is built and what it must satisfy
```

## Try it

```bash
paperkit build                # in Docker; the first run builds the image
paperkit build --no-docker    # with the TeX Live installed on this machine
paperkit zip                  # paper-sources.zip, with paper.bbl next to paper.tex
```

## What it shows

- **An excused bibliography entry.** `references.bib` holds `extended`,
  which this paper does not cite. Rather than switching the unused-entry
  check off, `[checks.unused_bib] ignore` names the key, and the check
  stays on for the rest of the file.
- **A cap on the whole PDF.** LNCS page counts include the references, so
  the file sets `total = 15`.
- **What the profile adds.** `lncs` puts `llncs.cls`, `splncs04.bst` and the
  `.bbl` in the archive, which Springer compiles without running BibTeX.
- **A font the image had to learn.** llncs separates the keywords with
  `\textperiodcentered`, a glyph the OT1 encoding lacks, so LaTeX sets it
  from the T1 Computer Modern fonts. Those come from `cm-super`, which the
  paperkit image installs; without it they are bitmaps, and the Type 3
  check says so. This example is how that was found.
- **A bibliography held to one format.** `paperkit bibtidy` rewrites
  `references.bib` the way bibtex-tidy does with the profile's arguments,
  and the check reports when it drifts, so a diff of the file shows a change
  of content and nothing else.

## Making it yours

Copy the directory, rename `paper.tex` and `[project] main`, replace the
sections, set `total` to the volume's number, and empty `ignore` once the
extended version is written. `paperkit init --profile lncs` writes a
configuration like this one into an existing project.
