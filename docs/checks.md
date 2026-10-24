# Checks reference

`paperkit build` runs the checks after a successful build, and `paperkit
check` runs them again on existing output without rebuilding. Both run in the
Docker image by default, where every tool is installed; `--no-docker` uses the
host's tools instead.

Each check reports one of four states:

| State | Meaning | Effect on the verdict |
|---|---|---|
| clean | Nothing found | none |
| warning | Something to look at | "Build OK with warnings" |
| error | Something that will cost you | "Build has errors" |
| skipped | The tool or the input was missing | counted as a warning, so it never passes silently |

A check that cannot run is deliberately not reported as clean. The one
exception is a check the configuration switches off, or one with nothing to
do, such as the bibliography checks in a project with no `bib` set: those are
clean and say why.

The page-limit check is advisory: it prints in red when you are over, but it
does not turn the verdict into "Build has errors", because being over the
limit is a fact about the paper rather than a defect in the build.

## Exit status

`paperkit build` and `paperkit check` exit with the verdict they printed:

| Situation | Exit status |
|---|---|
| Everything clean | 0 |
| Warnings or skipped checks | 0 |
| Any error, or a target that produced no PDF | 1 |
| Over a page limit | 0, since the page check is advisory |
| Any of the above, with `--strict` | 1 unless everything is clean |

The default is deliberately forgiving: a paper with three overfull boxes is
still a paper you can submit, and failing on that trains people to ignore the
exit status. `--strict` is for a paper repository's own CI, where a new
warning, a check that could not run, or going over the limit should all stop
the pipeline.

The status travels out of the container, so `paperkit check` in Docker
reports what the inner run found.

## The checks

| Check | Catches | Needs | Switch |
|---|---|---|---|
| LaTeX | Errors and warnings in `<main>.log` | - | always on |
| BibTeX or Biber | Errors and warnings in `<main>.blg` | - | runs when the build wrote a `.blg` |
| Toolchain | A PDF built by a different TeX Live than the configured one | - | `[texlive] source = "upstream"` |
| Boxes | Overfull and underfull boxes | - | `[checks] overfull_boxes` |
| Fonts | Unembedded fonts, and Type 3 bitmap fonts | `pdffonts` | `[checks] font_embedding`, `no_type3` |
| Non-ASCII | Non-ASCII bytes in the sources | - | `[checks] non_ascii` |
| Trailing whitespace | Lines ending in spaces | - | `[checks] trailing_whitespace` |
| Final newline | Files not ending in exactly one newline | - | `[checks] final_newline` |
| Unused bib entries | Entries no target cites | - | `[checks] unused_bib` |
| BibTeX tidy | A bibliography bibtex-tidy would reformat, and duplicate entries | `bibtex-tidy` | `[checks] bibtex_tidy` |
| Pages/Limit | A paper over its page budget | `pdfinfo`, `pdftotext` | `[page_limits]` |

### LaTeX, BibTeX and Biber logs

Reads the log the build wrote and reports its errors and warnings. The label
says Biber or BibTeX depending on the backend, so the report names the tool
that actually ran. A log that does not exist, because that stage never ran,
contributes nothing rather than an error.

### Toolchain

Only with `[texlive] source = "upstream"`. The report's TeX Live line comes
from the first line of the build log, not from asking the local binary, so it
describes the engine that made the PDF. This check compares that banner with
the configured TeX Live and warns when they cannot be the same: a
distribution-patched banner such as `TeX Live 2022/dev/Debian` means the PDF
came from the host, usually from a `--no-docker` build, not from the pinned
image. A snapshot accepts its own year or the one before, since a snapshot
taken in January still carries the previous release.

### Fonts

Lists the PDF's fonts with `pdffonts`. An unembedded font is an error:
publishers reject such a PDF, and it renders with substituted glyphs on a
machine that lacks the font. A Type 3 font is a warning: it is embedded, so
the PDF is valid, but Type 3 fonts are bitmaps that print poorly and search
badly.

Type 3 fonts usually come from one of two places. matplotlib emits them by
default, which `matplotlib.rcParams["pdf.fonttype"] = 42` fixes by switching
to TrueType. METAFONT bitmap fonts appear when a Computer Modern variant is
not available as Type 1, which installing `cm-super` fixes.

Every run writes the full listing to `<output_dir>/<main>/fonts.txt`. When
Type 3 fonts are found, the check also reports which pages they are on, so
you can find the offending figure with
`pdffonts -f <page> -l <page> <main>.pdf`.

Set `no_type3 = false` to keep the embedding check and drop the Type 3
warning.

### Non-ASCII, trailing whitespace, final newline

Source hygiene across the main files and `content_dirs`. Non-ASCII characters
are worth avoiding in LaTeX sources because a stray typographic quote or
en dash behaves differently across engines and encodings; the check prints the
file, the line number and the line, so the fix is mechanical. Use the LaTeX
spellings instead: `--`, `---`, `\'{e}`.

### Unused bib entries

An entry is unused when no target that uses its bib file cites it. paperkit
takes the truth from the build, not from a regex over the sources: for each
target it reads `\bibdata` and `\citation` from the `.aux` (following
`\@input`, and treating `\nocite{*}` as using everything), or the `.bcf` when
biber is configured. Entries listed in `ignore` are never reported, and
`@string`, `@preamble` and `@comment` blocks are not entries.

With several mains sharing one bib file the result is reported once per bib
file, not once per target, so an entry cited only by the extended version is
not reported as unused when you check the short one.

When only some targets are built or checked, the others still have to be
accounted for. paperkit uses their existing `.aux` if it is newer than every
source that could change it; failing that, and with `draft_pass = true`, it
runs one draft pass (no PDF) into a temporary directory to learn their
citations. If that is off, fails, or no engine is installed, those entries are
reported as "other targets not checked" rather than as unused. The check never
claims an entry is unused on incomplete information.

### BibTeX tidy

Runs bibtex-tidy on a copy of the bibliography with the profile's arguments
and reports whether the file is already tidy, plus any duplicate entries it
finds. Nothing is modified: `paperkit bibtidy` is the command that rewrites
the file, and it uses the same arguments, so a tidy run always satisfies the
check.

bibtex-tidy needs a terminal to produce output; paperkit allocates one in the
container, which is why the check is reliable there and can be skipped on a
host without the tool.

### Pages and limits

Counts the pages of the PDF and the pages of content before the references and
the acknowledgments, and compares them with `[page_limits]`. The sections are
found by their headings, first in the `.aux` table of contents and then by
scanning the text with `pdftotext`, so a starred `\section*{Acknowledgment}`
that writes no TOC entry is still found, as are small-caps headings that
extract as `R EFERENCES`. Reading order comes from `pdftotext`, so one-column
and two-column layouts both work.

A section that begins mid-page counts that page against the budget. By
default the references and the acknowledgments are both exempt and the budget
ends at whichever comes first; `ack_counts_as_content = true` makes the
references the only exempt tail, and the report then says "acks counted".

## Turning a check off

Every check is a key in `[checks]` (see
[configuration.md](configuration.md)), so switching one off is one line:

```toml
[checks]
non_ascii = false          # a paper with names that need accents in the source
no_type3 = false           # keep the embedding check, accept bitmap fonts
unused_bib = false         # or: [checks.unused_bib] ignore = ["key"]
```

Prefer narrowing a check to switching it off: `ignore` for a single bib entry
that is staged for a later version, `no_type3 = false` rather than
`font_embedding = false` when a figure's bitmap fonts are acceptable.
