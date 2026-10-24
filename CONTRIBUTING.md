# Contributing to paperkit

Thanks for considering a contribution. Bug reports, papers that paperkit
mishandles, and pull requests are all welcome.

## Getting set up

paperkit needs Python 3.12 or newer, and Docker for the container builds.
[uv](https://docs.astral.sh/uv/) manages the development environment:

```bash
git clone https://github.com/apaolillo/paperkit
cd paperkit
uv sync            # creates .venv with the tool versions from uv.lock
```

To run your working copy against a real paper, install it in editable mode
into a virtual environment of your own and call `paperkit` from the paper's
directory.

## Before you open a pull request

Run the full check suite:

```bash
./scripts/all_checks.sh
```

It verifies the copyright headers, formats the code, lints it, type-checks it
and runs the tests. The formatter rewrites files in place, so check
`git status` afterwards and include anything it changed.

CI runs the same script as `./scripts/all_checks.sh --check` on Python 3.12,
3.13 and 3.14. In that mode nothing is rewritten and an unformatted file is
an error, so run the suite locally before pushing.

What the suite does not check, but reviewers will:

- **Tests.** New behaviour comes with a test. The suite runs in about a
  second and does not need Docker or a TeX installation: keep it that way by
  testing the pure functions (`pages.content_end_pages`,
  `texlive.update_config_text`, ...) rather than driving a build.
- **ASCII only.** Source, comments and documentation stay ASCII. The report
  prints symbols through `\u` escapes.
- **Copyright header.** Every `.py` file starts with the two-line copyright
  notice and `SPDX-License-Identifier: MIT`. Copy it from any existing file.
- **Nothing project-specific.** paperkit is used across unrelated papers, so
  no venue names, no paper titles and no private paths in the code or the
  tests.
- **Documentation.** A user-visible change updates `README.md`, and adds an
  entry under `## [Unreleased]` in `CHANGELOG.md` (create that section if the
  previous release removed it).

## Commit messages

Follow [How to Write a Git Commit Message](https://cbea.ms/git-commit/): a
capitalized imperative subject of at most 50 characters, a blank line, then a
body wrapped at 72 characters explaining what changes and why, not how. The
existing history is the reference.

## Sign your work

paperkit uses the [Developer Certificate of Origin](https://developercertificate.org/).
It is a short statement that you wrote the patch, or otherwise have the right
to submit it under the project's license. Certify it by adding a line to each
commit message:

```
Signed-off-by: Your Name <your.email@example.com>
```

`git commit -s` adds it for you, using your configured name and email. Use
your real name, and the same identity across a series of commits.

## Scope and licensing

Contributions are accepted under the MIT license of the project; see
[LICENSE](LICENSE). The copyright is held by the Vrije Universiteit Brussel.
Where the project is heading is sketched in [ROADMAP.md](ROADMAP.md), and
[MAINTAINERS.md](MAINTAINERS.md) says who to expect a review from.
