# Examples

Complete paper projects, one per profile, that paperkit builds clean. Each
is a starting point to copy: sources laid out the way a real paper is, a
`.paperkit.toml` that comments every choice, and a README that says what the
project shows and what to change for your own paper.

| Example | Engine | Profile | Shows |
|---|---|---|---|
| [`minimal`](minimal/) | pdflatex | `base` | The smallest project: one file, no bibliography, a three-key configuration, and the report. Start here. |
| [`acm`](acm/) | pdflatex | `acm` | A paper and its supplementary material from one tree: `content/` and `header/`, a TikZ figure, a bibliography shared and checked across both targets, the ACM page rule, a pinned TeX Live, the `.bbl` in the archive. |
| [`ieee`](ieee/) | pdflatex | `ieee` | An IEEEtran conference paper: the font check PDF eXpress relies on, a cap on the whole PDF, the `.bbl` in the archive. |
| [`lncs`](lncs/) | pdflatex | `lncs` | A Springer llncs paper: a bibliography entry excused by key for the extended version, a cap on the whole PDF, the `.bbl` for Springer. |
| [`usenix`](usenix/) | pdflatex | `usenix` | A two-column submission: the USENIX page rule, `--strict` for the last check, a bibliography kept in reading order. |
| [`typst`](typst/) | typst | `typst` | A plain Typst paper with sections in `content/` and a BibTeX bibliography, in an image without TeX Live. |
| [`typst-ieee`](typst-ieee/) | typst | `typst-ieee` | Universe's `charged-ieee`: a declared package baked into the image, a font the image installs. |
| [`typst-acm`](typst-acm/) | typst | `typst-acm` | Universe's `faithful-acmart`: fonts that travel with the paper, the ACM page rule in Typst. |

## Running one

```bash
git clone https://github.com/apaolillo/paperkit
cd paperkit/examples/acm
paperkit build                # in Docker; the first run builds the image
paperkit build --no-docker    # with the TeX Live, or typst, installed on this machine
paperkit check                # the checks again, on the existing build output
paperkit zip                  # the submission archive
```

paperkit itself comes from PyPI: `uv tool install paperkit`, `pipx install
paperkit`, or `uvx paperkit build` for a one-off. Docker is the only other
requirement; the image an example builds holds its engine, the check tools
and paperkit, composed from the example's configuration.

Each example builds clean, and inside the image clean under `--strict`: no
warning, no skipped check, within its page budget. Built on the host, the
report adds one row: the toolchain used was not the pinned one.

## Starting your paper from one

Copy the directory whose venue is yours, rename the main file and the
`[project] main` key, replace the sections, and set the page budget to the
call's number; each README has the list. Or keep your layout and run
`paperkit init --profile NAME` (`--typst` for Typst) in your project, which
writes a configuration like the example's.

The configuration files are the readable form of the
[configuration reference](../docs/configuration.md): each key a paper at
that venue reaches for, with the reason next to it. What each check catches
is in the [checks reference](../docs/checks.md).

## These are tests too

`scripts/build_fixtures.sh --docker` builds every example through its image
and holds it to `--strict`, and the `fixtures` workflow runs that weekly and
whenever the build code or an example changes. The deliberately broken
projects live under `tests/papers/`, not here.
