# The Typst example

A plain Typst paper, under the `typst` profile: sections in `content/`, a
BibTeX bibliography, no packages and no extra fonts. It builds in an image
without TeX Live, around a pinned Typst release.

```
paper.typ          the paper: page and text settings, and the sections by name
content/           abstract, sections, acknowledgments
references.bib     the bibliography (BibTeX; Hayagriva .yml works too)
.paperkit.toml     how it is built and what it must satisfy
```

## Try it

```bash
paperkit build                # in Docker; the first run builds the Typst image
paperkit build --no-docker    # with the typst installed on this machine
paperkit zip                  # paper-sources.zip: the files the compilation read
```

Built on the host with a typst other than the pinned release, the report
says so in its toolchain row; in the image the two agree.

## What it shows

- **One engine switch.** `engine = "typst"` and the main file is
  `paper.typ`; the rest of the configuration means the same as for LaTeX.
- **Fonts and packages made explicit.** System fonts are off, so the build
  sees the fonts Typst embeds plus what the project lists under `fonts` and
  what the image installs, the same on every machine. Packages from Typst
  Universe go under `packages` so the image fetches them once. This paper
  needs neither; the two Typst venue examples show both.
- **The checks on Typst's own truth.** Citations come from `typst query`,
  the diagnostics are the log, and the archive is the dependency list of
  the compilation, so it holds exactly the sources.
- **A small image.** No TeX Live: the pinned compiler, the check tools and
  paperkit, about half a gigabyte.

## Making it yours

Copy the directory, rename `paper.typ` and `[project] main`, replace the
sections; list `fonts` and `packages` as the paper comes to need them.
`paperkit init --typst` writes a configuration like this one into an
existing project.
