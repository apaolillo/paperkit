# The Typst ACM example

A paper in Typst Universe's ACM template, `faithful-acmart`, under the
`typst-acm` profile. It is the example for a Typst paper that carries its
own fonts, and for the ACM page rule in Typst.

```
paper.typ          the paper: the template import and its settings, the sections by name
content/           abstract, sections, acknowledgments
fonts/             Libertinus Sans and Math, Inconsolata, with their licence
references.bib     the bibliography
.paperkit.toml     how it is built and what it must satisfy
```

## Try it

```bash
paperkit build                # in Docker; the first run builds the image, package included
paperkit build --no-docker    # with the typst on this machine; the package downloads once
paperkit zip                  # paper-sources.zip: the files the compilation read, fonts/ included
```

## What it shows

- **Fonts that travel with the paper.** The template sets Libertinus Sans
  and Math and Inconsolata, which Typst does not embed and the package does
  not ship. They sit under `fonts/` with their licence, `[typst] fonts`
  points there, and system fonts are off, so the paper renders the same on
  every machine. The font check then sees every family embedded.
- **A declared package**, fetched at image build so the build is offline.
- **The ACM page rule in Typst.** `before_refs = 12` with
  `ack_counts_as_content = true`, measured against the headings from
  `typst query`, the same source as the citations.
- **An archive with the fonts.** `paperkit zip` adds the font directories
  to the dependency list, so the archive compiles elsewhere with the same
  fonts.

## Making it yours

Copy the directory with `fonts/`, rename `paper.typ` and `[project] main`,
replace the sections, and set `before_refs` to the call's number.
`paperkit init --typst --profile acm` writes a configuration like this one
into an existing project.
