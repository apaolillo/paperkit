# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""The fixture papers and the examples must stay loadable, whatever happens
to the config format.

Building them needs TeX and belongs to scripts/build_fixtures.sh; what the
unit suite can check is that each project still parses and resolves, and
that the examples keep the shape a new user is promised.
"""

from pathlib import Path

import pytest

from paperkit.config import load_config
from paperkit.profiles import profile_names

PAPERS = Path(__file__).resolve().parent / "papers"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _names(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


NAMES = _names(PAPERS)
EXAMPLE_NAMES = _names(EXAMPLES)

needs_examples = pytest.mark.skipif(not EXAMPLES.is_dir(), reason="examples/ is not in the sdist")


def test_the_fixtures_are_there() -> None:
    assert NAMES == [
        "acmart",
        "ieee",
        "lncs",
        "minimal",
        "typst-acm",
        "typst-ieee",
        "typst-minimal",
        "usenix",
        "warnings",
    ]


def _check_project(root: Path) -> None:
    config = load_config(root / ".paperkit.toml")
    assert config.mains, "a project names at least one main"
    for main in config.mains:
        assert config.main_file(main).is_file(), f"{main}{config.main_suffix} is missing"
    if config.bib:
        assert (config.root / config.bib).is_file()
    for content_dir in config.content_dirs:
        assert (config.root / content_dir).is_dir(), f"content_dirs names {content_dir}"


@pytest.mark.parametrize("name", NAMES)
def test_each_fixture_config_loads(name: str) -> None:
    _check_project(PAPERS / name)
    assert load_config(PAPERS / name / ".paperkit.toml").mains == ["paper"]


def test_the_warnings_fixture_still_trips_the_source_checks() -> None:
    # If someone tidies these files, the fixture stops testing anything.
    notes = (PAPERS / "warnings" / "content" / "notes.tex").read_bytes()
    assert any(b > 127 for b in notes), "the non-ASCII character is gone"
    assert not notes.endswith(b"\n"), "the missing final newline came back"
    body = (PAPERS / "warnings" / "content" / "body.tex").read_text()
    assert any(line.rstrip("\n").endswith(" ") for line in body.splitlines(keepends=True))
    assert "uncited" in (PAPERS / "warnings" / "refs.bib").read_text()


@needs_examples
def test_every_profile_has_an_example() -> None:
    # The examples are named after the profiles they show; base is shown by
    # the minimal one. A new profile comes with an example to copy.
    expected = {"minimal" if name == "base" else name for name in profile_names()}
    assert set(EXAMPLE_NAMES) == expected


@needs_examples
@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_each_example_is_a_complete_project(name: str) -> None:
    root = EXAMPLES / name
    _check_project(root)
    config = load_config(root / ".paperkit.toml")
    assert config.profile_name == ("base" if name == "minimal" else name)
    # What a new user is promised: a README that says how to run it, a
    # commented configuration, and build output kept out of git.
    readme = (root / "README.md").read_text()
    assert "paperkit build" in readme
    toml = (root / ".paperkit.toml").read_text()
    assert toml.lstrip().startswith("#"), "the configuration opens with what it is for"
    assert "/out/" in (root / ".gitignore").read_text()


@needs_examples
@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_examples_are_ascii_with_final_newlines(name: str) -> None:
    # The source checks paperkit runs on them, applied to everything else in
    # the directory too, README and configuration included. Build output is
    # not tracked and not checked.
    text = {".tex", ".typ", ".bib", ".toml", ".md", ".txt", ".gitignore"}
    for path in (EXAMPLES / name).rglob("*"):
        if not path.is_file() or path.suffix not in text or "/out/" in str(path):
            continue
        if "fonts" in path.parts:
            continue  # a font licence is reproduced verbatim, dashes included
        data = path.read_bytes()
        assert all(b < 128 for b in data), f"{path} is not ASCII"
        assert data.endswith(b"\n") and not data.endswith(b"\n\n"), f"{path}: final newline"
        assert not any(line.endswith(b" ") for line in data.splitlines()), f"{path}: trailing"
