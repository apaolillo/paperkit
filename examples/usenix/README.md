# The USENIX example

A two-column paper in the shape of a USENIX submission, under the `usenix`
profile. It is the example for the page rule those calls state: a budget of
content pages that excludes the references and nothing else.

```
paper.tex          the paper: title block and the sections by name
content/           abstract, sections, acknowledgments
references.bib     the bibliography, in reading order
.paperkit.toml     how it is built and what it must satisfy
```

USENIX's style file is not in TeX Live, so the example is a plain two-column
article with the same geometry. A real submission drops `usenix2019_v3.sty`
next to `paper.tex` and loads it; the archive pattern `*.sty` picks it up.

## Try it

```bash
paperkit build                # in Docker; the first run builds the image
paperkit build --strict       # the same, exiting 1 on a warning or a page overrun
paperkit build --no-docker    # with the TeX Live installed on this machine
```

## What it shows

- **The USENIX page rule.** `before_refs = 12` with
  `ack_counts_as_content = true`: the budget ends where the references
  start, a references section that starts mid-page counts that page, and the
  acknowledgments are content. The profile sets the second key; the file
  writes it out.
- **`--strict` for the last check.** A page overrun is advisory by default,
  so a draft that is a page over still builds. Before submission, or in CI,
  `--strict` makes it exit 1, along with any warning or skipped check.
- **A bibliography in reading order.** `bibtex_tidy.sort = false` keeps the
  entries as written while holding the file to one formatting.
- **An archive for the artifact.** Submission is a PDF, but the sources,
  the bibliography and the style file zip up for the artifact evaluation or
  the lab's records.

## Making it yours

Copy the directory, add the style file the call points to, rename
`paper.tex` and `[project] main`, replace the sections, and set
`before_refs` to the call's number. `paperkit init --profile usenix` writes
a configuration like this one into an existing project.
