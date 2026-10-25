# Configuration reference

paperkit reads `.paperkit.toml` from the current directory or the nearest
parent that has one; `paperkit --config PATH` overrides the search. That
file's directory is the project root, and every path in it is relative to
that root.

Every key is optional. The defaults below are what paperkit uses when the key
is absent, so the shortest useful config is an empty file: one target called
`main`, built with pdflatex in Docker.

`paperkit init` writes a starting point with the common keys filled in.

## [project]

| Key | Type | Default | Meaning |
|---|---|---|---|
| `main` | string or list | `"main"` | Main `.tex` file(s), without the extension |
| `mains` | string or list | unset | Alias of `main`; both are merged if both appear |
| `content_dirs` | list | `["content"]` | Directories holding the other `.tex` sources |
| `bib` | string | `""` | The bibliography file; empty disables the bib checks |

A target name may be a glob, matched against `<root>/<pattern>.tex`:
`main = "paper*"` picks up every matching file, sorted, and a glob matching
nothing is an error rather than a silent empty build. Duplicates are dropped,
and the first name is the project's default target, used by `paperkit zip`
when `[zip] name` is unset.

`content_dirs` says where the source checks (non-ASCII, trailing whitespace,
final newline) look, and which files make an `.aux` stale for the unused-bib
check. The main files themselves are always included.

## [build]

| Key | Type | Default | Meaning |
|---|---|---|---|
| `engine` | string | `"pdflatex"` | `pdflatex`, `lualatex`, `xelatex`, or `typst` (see `[typst]`) |
| `passes` | integer | `3` | Engine passes per build |
| `shell_escape` | bool | `true` | Pass `-shell-escape`, which `minted` and `svg` need |
| `bibtex` | bool | `true` | Run bibtex after the first pass |
| `biber` | bool | `false` | Run biber instead of bibtex, for biblatex |
| `output_dir` | string | `"out"` | Build directory; each target writes `<output_dir>/<main>/` |
| `jobs` | integer | CPU count | Targets built in parallel |
| `source_date_epoch` | integer, string or `"git"` | `"git"` | Timestamp every tool builds with |

Three passes resolve references and citations for most papers. A fourth lets
acmart's `pbalance` balance the last page, at the cost of a slower build.

Set `jobs = 1` when one target includes another's PDF (`\includepdf`), so the
included one is finished before the including one starts.

`source_date_epoch` pins the PDF's dates, its font subset tags and its trailer
id, so the same sources produce byte-identical PDFs. It accepts a Unix epoch
(`1792877220`), an ISO date (`"2026-10-29"`), or `"git"`, which uses the
committer date of `HEAD`. An external `SOURCE_DATE_EPOCH` in the environment
wins over the config, so a release pipeline can impose its own. Outside a git
repository, `"git"` falls back to the current time and the build warns that it
will not be reproducible.

## [docker]

| Key | Type | Default | Meaning |
|---|---|---|---|
| `base_image` | string | `"ubuntu:26.04"` | Image the build image is layered on |
| `image_name` | string | `"paperkit-builder"`, `"paperkit-typst-builder"` for Typst | Tag of the built image |
| `extra_packages` | list | `[]` | Extra APT packages for this project |
| `debconf_selections` | list | `[]` | debconf answers pre-seeded before those packages install |

Every engine, biber, and all the check tools are installed regardless of what
the config selects, so switching engine or bib backend never needs an image
rebuild.

Give `image_name` a project-specific value if you work on several papers: the
image is cached under that tag, and sharing one tag between projects with
different `extra_packages` means rebuilding it each time you switch.

`debconf_selections` answers the questions a package would otherwise ask, for
instance accepting a font licence:

```toml
[docker]
extra_packages = ["ttf-mscorefonts-installer"]
debconf_selections = ["ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true"]
```

## [texlive]

| Key | Type | Default | Meaning |
|---|---|---|---|
| `source` | string | `"distro"` | `"distro"` for the base image's packages, `"upstream"` for install-tl |
| `repository` | URL | unset | Explicit tlnet repository; highest precedence |
| `snapshot` | `"YYYY-MM-DD"` | unset | Dated texlive.info snapshot |
| `year` | integer | unset | Final repository of a closed TeX Live release |
| `tlpdb_sha512` | 128 hex chars | unset | Expected checksum of the repository's package database |
| `scheme` | string | `"small"` | install-tl scheme |
| `collections` | list | `[]` | Collections installed with tlmgr afterwards, without the `collection-` prefix |
| `packages` | list | `[]` | Individual packages installed with tlmgr |
| `docs` | bool | `false` | Install package documentation |
| `sources` | bool | `false` | Install package sources |

Unknown keys in this table are an error, not a typo that silently does
nothing, and so are `snapshot` and `year` together.

With `source = "distro"` the TeX Live version is whatever the base image
ships, and it changes when the image does. With `source = "upstream"`,
paperkit runs the official `install-tl` against a tlnet repository; a dated
`snapshot` then gives the same package set on every rebuild. `tlpdb_sha512` is
verified before anything is installed, so a repository that changed under you
fails the image build instead of producing a different TeX Live.

Resolution order is `repository` > `snapshot` > `year` > the live CTAN mirror,
and the last one warns, because a live mirror is not reproducible.

`scheme` is one of `basic`, `context`, `full`, `gust`, `infraonly`, `medium`,
`minimal`, `small`, `tetex`. Collections are named as TeX Live names them, so
`mathscience`, not Debian's `science`; paperkit rejects the Debian spelling
with the right one in the message. The scheme's own collections are always
kept, and the listed ones are added to them.

`paperkit init` pins a snapshot verified for the installed paperkit release,
and `paperkit texlive-update` moves `snapshot` and `tlpdb_sha512` to the
newest published one. It is the only command that uses the network.

## [typst]

Only read when `[build] engine = "typst"`. A Typst project builds in an image
without TeX Live: the pinned Typst binary, the check tools and paperkit.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `version` | `"X.Y.Z"` | the release verified for this paperkit | Typst release installed in the image |
| `sha256` | 64 hex chars | known for the default version | Checksum of the release tarball for this machine's architecture; required for any other version |
| `build_from_source` | bool | `false` | `cargo install --locked typst-cli` pinned to the version's tag, instead of the release binary |
| `fonts` | list | `[]` | Directories of fonts, relative to the root, searched recursively (`--font-path`) |
| `ignore_system_fonts` | bool | `true` | Do not search the machine's fonts; the embedded fonts, `fonts`, and fonts installed in the image are all a build sees |
| `packages` | list | `[]` | Universe packages as imported, `"@preview/charged-ieee:0.1.4"`, downloaded into the image when it is built |
| `packages_dir` | string | unset | A local packages tree on the host (namespaces as subdirectories), mounted read-only into the container |
| `pdf_standard` | string | unset | One of typst's `--pdf-standard` values, such as `a-2b`, for venues that require PDF/A |
| `extra_args` | list | `[]` | Further `typst compile` arguments, verbatim |

Unknown keys are an error, as for `[texlive]`.

Reproducibility works differently from LaTeX and needs less: Typst honors
`SOURCE_DATE_EPOCH` and nothing else varies between two compiles of the same
sources, with two exceptions that these keys close. Fonts: Typst searches the
machine's fonts by default and substitutes silently when a family is missing,
so the same sources render differently on another machine; with
`ignore_system_fonts = true` a build sees only the fonts Typst embeds
(Libertinus Serif, New Computer Modern, DejaVu Sans Mono), the project's own
`fonts` directories, and the fonts installed in the image by `[docker]
extra_packages` or a profile, which are part of the pinned environment; a
missing family is reported as a warning with the file and line that asked
for it. Packages:
an import from Typst Universe is fetched over the network the first time it
is used; listing it under `packages` fetches it when the image is built, so
builds themselves need no network. A package the sources import without
declaring it still works, downloaded at build time, and the report says so.

`build_from_source` exists for a version without a release binary. It
produces the same compiler but not the same bytes, needs a Rust toolchain in
the image, and takes minutes rather than seconds, so the release binary is the
default. `passes`, `bibtex`, `biber` and `[zip] include_bbl` mean nothing to a
Typst build (one pass, bibliography built in) and are ignored with a note.

## [checks]

| Key | Type | Default | Meaning |
|---|---|---|---|
| `non_ascii` | bool | `true` | Flag non-ASCII characters in the sources |
| `trailing_whitespace` | bool | `true` | Flag lines ending in spaces |
| `final_newline` | bool | `true` | Require exactly one trailing newline per file |
| `font_embedding` | bool | `true` | Require every font in the PDF to be embedded |
| `no_type3` | bool | `true` | Also warn about Type 3 (bitmap) fonts |
| `overfull_boxes` | bool | `true` | Count overfull and underfull boxes |
| `unused_bib` | bool or table | `true` | Report bibliography entries nothing cites |
| `bibtex_tidy` | table | see below | Check the bibliography's formatting |

`[checks.unused_bib]`:

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | bool | `true` | Run the check |
| `ignore` | list | `[]` | Keys never reported, such as an entry staged for later |
| `draft_pass` | bool | `true` | Resolve targets outside this run with one draft LaTeX pass |

`[checks.bibtex_tidy]`:

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | bool | `true` | Run the check |
| `version` | string | `"1.14.0"` | bibtex-tidy version installed in the image |
| `sort` | bool | `true` | Sort entries by key and fields within entries |

`sort` is the default for `paperkit bibtidy` as well, so the command and the
check never disagree about what a tidy file looks like; `--sort` and
`--no-sort` override it for one run.

What each check catches, and when it is skipped rather than run, is in
[checks.md](checks.md).

## [page_limits]

| Key | Type | Default | Meaning |
|---|---|---|---|
| `total` | integer | unset | Maximum pages in the PDF, references included |
| `before_refs` | integer | unset | Maximum pages of content before the references |
| `before_ack` | integer | unset | Maximum pages of content before the acknowledgments |
| `ack_counts_as_content` | bool | `false` | Count the acknowledgments as content |
| `refs_pattern` | regex | `(?i)\b(references\|bibliography)\b` | How the references heading is recognized |
| `ack_pattern` | regex | `(?i)acknowledg` | How the acknowledgments heading is recognized |

Without this table the pages are counted and reported, but nothing is flagged.
A section that starts mid-page counts that page against the budget, which is
how a programme chair counts it.

By default the references and the acknowledgments are both exempt and the
budget ends at whichever comes first. Venues that exempt only the references,
which is most ACM and USENIX calls, want `ack_counts_as_content = true`.

The patterns only matter for a paper whose headings are in another language or
worded unusually, for instance `refs_pattern = "(?i)\\b(references|literatur)\\b"`.

## [zip]

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | string | the first main | Archive base name: `<name>-sources.zip` |
| `include` | list | `[]` | Glob patterns to archive, relative to the root |
| `exclude` | list | `["*.aux", "*.log", "*.out", "*.blg", "*.bbl"]` | Basename patterns dropped from the result |
| `include_bbl` | bool | `false` | Also ship each included main's compiled bibliography |

`{main}` in an include pattern expands once per target, so `"{main}.tex"`
covers every main of the project. `exclude` matches basenames, not paths.

`include_bbl` copies `<output_dir>/<main>/<main>.bbl` next to that main's
`.tex` in the archive, for publishers who compile the sources without running
BibTeX. It ignores `exclude`, so the default `*.bbl` entry does not undo it. A
missing `.bbl` is an error that leaves the previous archive untouched, and a
`.bbl` older than its sources is a warning.

Archives are reproducible: entry timestamps come from the build timestamp
rather than the files' mtimes, which git does not preserve, so the same
sources zip to the same bytes on another machine.

## [profile]

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | string | `"acm"` | `base`, `acm`, `ieee`, `lncs`, `usenix`, `typst`, `typst-acm` or `typst-ieee` |

A profile carries what a venue's document class implies for a project, as
defaults laid underneath the file: a key the file sets wins, and a list the
file sets replaces the profile's list rather than merging with it.

| Profile | Sets, unless the file does |
|---|---|
| `base` | `[zip] include = ["{main}.tex", "content/**/*.tex", "**/*.bib", "*.sty"]` |
| `acm` | base's list plus `acmart.cls` and `ACM-Reference-Format.bst`; `[zip] include_bbl = true`; `[build] passes = 4`; `[page_limits] ack_counts_as_content = true` |
| `ieee` | base's list plus `IEEEtran.cls` and `IEEEtran.bst`; `[zip] include_bbl = true` |
| `lncs` | base's list plus `llncs.cls` and `splncs04.bst`; `[zip] include_bbl = true` |
| `usenix` | `[page_limits] ack_counts_as_content = true` |
| `typst` | `[zip] include = ["{main}.typ", "**/*.typ", "**/*.bib", "**/*.yml", "**/*.yaml", "fonts/**"]`, `include_bbl = false` |
| `typst-ieee` | as `typst`; installs `fonts-texgyre` in the image for `charged-ieee` |
| `typst-acm` | as `typst`; `[page_limits] ack_counts_as_content = true` |

The reasoning: ACM's TAPS, IEEE's PDF eXpress and Springer's LNCS pipeline
all compile the submitted sources without running BibTeX, so the archive must carry the `.bbl`, and a
project that pins its own copy of the class or style file must ship it, while
a pattern matching no file is simply skipped. The fourth pass lets acmart's
`pbalance` balance the last page. ACM and USENIX calls state the page limit
as "N pages, not including references", so the acknowledgments sit inside
the budget; IEEE and LNCS page rules vary by conference, so those profiles
leave `[page_limits]` alone. USENIX submission is a PDF and its style file
ships with the template, not TeX Live, so the `usenix` profile has nothing
to add to the archive beyond base's `*.sty`.

Because `acm`, `ieee` and `lncs` default `include_bbl` to true, `paperkit zip` in such
a project needs a build first, or `--no-bbl`.

`paperkit init --profile NAME` writes these values out explicitly, so the
generated file shows what a build will do rather than hiding it behind the
profile name.

## A complete example

```toml
[project]
main = "paper"
content_dirs = ["content", "figures"]
bib = "content/references.bib"

[build]
engine = "pdflatex"
passes = 3
shell_escape = true
bibtex = true
output_dir = "out"
source_date_epoch = "git"

[docker]
base_image = "ubuntu:26.04"
image_name = "mypaper-builder"

[texlive]
source = "upstream"
snapshot = "2026-10-22"
tlpdb_sha512 = "f336dd94..."
scheme = "small"
collections = ["latexextra", "fontsrecommended", "fontsextra", "publishers"]

[checks]
non_ascii = true
bibtex_tidy = { enabled = true, version = "1.14.0", sort = true }

[checks.unused_bib]
ignore = ["staged_for_the_journal_version"]

[page_limits]
before_refs = 12
ack_counts_as_content = true

[zip]
include = ["{main}.tex", "content/**/*.tex", "content/references.bib", "figures/*.pdf"]
include_bbl = true

[profile]
name = "acm"
```
