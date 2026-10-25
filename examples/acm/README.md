# The ACM example

A paper in the ACM format and its supplementary material, built from one
source tree by one command. This is the example to copy for a conference
paper: it has the layout, the configuration and the checks a real submission
ends up needing, and it builds clean.

```
paper.tex                 the paper: names the pieces and their order
supplementary.tex         a second target, sharing header/ and the bibliography
header/                   packages, macros, authors
content/                  the sections, numbered to read like the table of contents
content/supplementary/    the appendix sections
content/references.bib    one bibliography for both targets
figures/tex/              figures as TikZ sources
.paperkit.toml            how the paper is built and what it must satisfy
```

## Try it

```bash
paperkit build                # both targets, in Docker; the first run builds the image
paperkit build paper          # one target, with its full report
paperkit build --no-docker    # with the TeX Live installed on this machine
paperkit check                # the checks again, on the existing build output
paperkit zip                  # paper-sources.zip, with the compiled .bbl next to each main
```

The first `paperkit build` composes the image from `.paperkit.toml`: Ubuntu,
a TeX Live installed from the dated snapshot the file pins, the check tools,
and paperkit itself. That takes a few minutes once; builds afterwards take
seconds. Output lands in `out/paper/` and `out/supplementary/`, and the PDFs
are copied next to the main files.

## What it shows

- **Two targets from one tree.** `mains` lists the paper and the
  supplementary material. They share the preamble and the bibliography, so
  the unused-entry check gathers the citations of both before calling an
  entry unused: `tlnet` is cited only in the appendix and is not reported.
- **A pinned TeX Live.** `[texlive]` names a snapshot and the checksum of its
  package database. Every rebuild of the image installs the same packages,
  and `source_date_epoch = "git"` makes two builds of one commit produce the
  same bytes. `paperkit texlive-update` moves the pin forward when you
  decide to.
- **The venue's rules as defaults.** The `acm` profile adds the class files
  and the compiled `.bbl` to the archive, builds with four passes so
  `pbalance` can balance the last page, and counts the acknowledgments as
  content, as ACM calls do. Each is written out in the file anyway, so the
  file shows what the build does.
- **A page budget.** `before_refs = 12` is the call's number. The report
  says how many pages the content takes and flags an overrun; `--strict`
  turns the overrun into a non-zero exit, for a pre-submission check in CI.
- **Title and abstract as text.** `out/paper/title.txt` and
  `out/paper/abstract.txt` are ready to paste into the submission form.
- **The report.** After the build, one table per check: LaTeX errors and
  warnings, boxes, fonts (with Type 3 called out), the three source checks,
  unused entries, bibtex-tidy, pages. A real paper reads this table after
  every build.

## Making it yours

1. Copy the directory and rename `paper.tex`; update `mains` and `[zip] name`.
   Drop `supplementary.tex` from `mains` if you have one document.
2. Replace `header/authors.tex` and the sections under `content/`.
3. Drop `nonacm` from the `\documentclass` line for the camera-ready and add
   the rights lines TAPS sends you.
4. Set `before_refs` to the call's limit, and `image_name` to something of
   yours.
5. Keep `out/` and the PDFs out of git; the `.gitignore` here does.

Or run `paperkit init --profile acm` in an existing project, which writes a
configuration like this one with the same TeX Live pin.
