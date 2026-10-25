# Releasing paperkit

This document records the exact steps to publish a new release of paperkit.

Prereqs:
- You have push access to the repo. No PyPI credentials are needed: the
  `release` workflow publishes through [Trusted Publishing](https://docs.pypi.org/trusted-publishers/),
  which is set up once (see the end of this file).
- `CHANGELOG.md` follows Keep a Changelog and Semantic Versioning.
- The version is maintained manually (PEP 440) in one place:
  `__version__` in `src/paperkit/__init__.py` (`pyproject.toml` reads it).
- `./scripts/all_checks.sh` passes on `main`, and the `checks` and `fixtures`
  workflows are green.
- `texlive.KNOWN_GOOD_SNAPSHOT` / `KNOWN_GOOD_TLPDB_SHA512` have been bumped
  to a snapshot verified with an image build (`paperkit texlive-update` on a
  project, then `paperkit build`), so `paperkit init` pins something current.
- [uv](https://docs.astral.sh/uv/) is installed.

Versioning Tag format: `v0.X.Y`

Date format: `YYYY-MM-DD`.

---

## 1) Prepare the release

1. Pick the version number `0.X.Y`.

2. Update `CHANGELOG.md`:
   - Add a new section `## [0.X.Y] - YYYY-MM-DD` under `[Unreleased]`.
   - Move curated changes from `[Unreleased]` into `0.X.Y`.

3. Bump the version in `src/paperkit/__init__.py`:
   ```python
   __version__ = "0.X.Y"
   ```

4. Sanity checks locally:

   ```bash
   ./scripts/all_checks.sh
   git clean -ndx
   git status
   ```

5. Create a short-lived release branch and commit:
    ```bash
    git checkout -b release
    git add -u
    git commit -s -m "Release 0.X.Y"
    git push -u origin release
    ```

6. Open the corresponding PR on GitHub. When CI is green, merge.

---

## 2) Tag the release

After the PR is merged:

```bash
git checkout main
git pull --prune
git tag -a "v0.X.Y" -m "Release v0.X.Y"
git push origin v0.X.Y
```

Tag from `main`, never from a local working branch: the tag is what gets
built and published.

---

## 3) Let the release workflow publish

Pushing the tag runs `.github/workflows/release.yml`:

1. `build` checks out the tag on a clean runner, runs `uv build` and
   `twine check`, and refuses to go on if the version inside the wheel is
   not the version in the tag.
2. `publish` waits for the `pypi` environment (approve it on GitHub if the
   environment has required reviewers), then uploads through Trusted
   Publishing. PyPI records a provenance attestation for each file.

Watch it with `gh run watch`. If `build` fails, fix on `main`, delete the
tag locally and remotely (`git tag -d v0.X.Y && git push origin :v0.X.Y`),
and tag again: a PyPI filename can never be reused, so nothing should be
uploaded until the build is right.

---

## 4) Verify the release

* PyPI page: [https://pypi.org/project/paperkit/](https://pypi.org/project/paperkit/),
  with the "Verified details" and provenance shown for the files.
* Clean install:

  ```bash
  uv tool install paperkit==0.X.Y
  paperkit --version
  ```
* Docker build with the published package. An installed paperkit installs the
  same version from PyPI inside the image, so this only works once the upload
  above is done:

  ```bash
  mkdir /tmp/paperkit-verify && cd /tmp/paperkit-verify
  paperkit init
  printf '\\documentclass{article}\n\\begin{document}\nHello.\n\\end{document}\n' > main.tex
  paperkit build
  ```
* Publish the GitHub Release from the tag, with the CHANGELOG section as its
  notes.
* Check that the README renders correctly on PyPI.
* Profit.

---

## One-time setup: Trusted Publishing

Done once per PyPI project; nothing to repeat per release.

1. On PyPI, project `paperkit` > Manage > Publishing > add a GitHub
   publisher: owner `apaolillo`, repository `paperkit`, workflow
   `release.yml`, environment `pypi`.
2. On GitHub, Settings > Environments > create `pypi`. Add yourself as a
   required reviewer if you want a human approval between the tag push and
   the upload; leave it without reviewers for a fully automatic release.

The API-token path still works as a fallback (`uvx twine upload dist/*`
from a fresh clone of the tag), but the workflow is the normal route, and
the only one that produces attestations.
