# The Typst IEEE example

A paper in Typst Universe's IEEE template, `charged-ieee`, under the
`typst-ieee` profile. It is the example for a Typst paper that imports a
package and needs a font Typst does not embed.

```
paper.typ          the paper: the template import and its settings, the sections by name
content/           abstract, sections, acknowledgment
references.bib     the bibliography
.paperkit.toml     how it is built and what it must satisfy
```

## Try it

```bash
paperkit build                # in Docker; the first run builds the image, package and font included
paperkit build --no-docker    # with the typst on this machine; the package downloads once into its cache
```

## What it shows

- **A declared package.** `[typst] packages` names the import, so the image
  build fetches it and the paper builds offline. The report has a packages
  row that says whether every package the compilation used was declared; an
  import nobody declared still builds, and that row says so.
- **A font from the image.** The template sets TeX Gyre Termes. The profile
  installs `fonts-texgyre` in the image, where paperkit makes it visible to
  Typst, so the PDF has the font and the font check sees it embedded.
  Without it, Typst would substitute silently; paperkit reports the family
  that was missing instead.
- **A cap on the whole PDF**, as IEEE calls state it.

## Making it yours

Copy the directory, rename `paper.typ` and `[project] main`, replace the
sections. Bump the version in the import and in `packages` together.
`paperkit init --typst --profile ieee` writes a configuration like this one
into an existing project.
