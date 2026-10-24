# Releasing paperkit

This document records the exact steps to publish a new release of paperkit.

Prereqs:
- You have push access to the repo and the PyPI project.
- `CHANGELOG.md` follows Keep a Changelog and Semantic Versioning.
- The version is maintained manually (PEP 440) in one place:
  `__version__` in `src/paperkit/__init__.py` (`pyproject.toml` reads it).
- `./scripts/all_checks.sh` passes on `main`, and the checks workflow is green.
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

---

## 3) Build artifacts locally

Use a fresh clone to avoid leaking local files into the archives:

```bash
git clone git@github.com:apaolillo/paperkit.git paperkit-release
cd paperkit-release/
git checkout v0.X.Y
uv build                   # creates dist/*.whl and dist/*.tar.gz
uvx twine check dist/*
```

Quick inspection:

* Confirm the wheel is `paperkit-0.X.Y-py3-none-any.whl` (pure Python).
* Confirm the tarball contains only the package, tests and top-level docs:
  ```bash
  tar tzf dist/paperkit-0.X.Y.tar.gz
  ```

---

## 4) Publish to PyPI

```bash
uvx twine upload dist/*
```

You will need a `~/.pypirc` or to paste your `__token__` API token when prompted.

---

## 5) Verify the release

* PyPI page: [https://pypi.org/project/paperkit/](https://pypi.org/project/paperkit/)
* Clean install:

  ```bash
  uv tool install paperkit==0.X.Y
  paperkit --help
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
* Check that the README renders correctly on PyPI.
* Profit.
