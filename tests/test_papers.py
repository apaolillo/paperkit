# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""The fixture papers must stay loadable, whatever happens to the config format.

Building them needs TeX and belongs to scripts/build_fixtures.sh; what the
unit suite can check is that each project still parses and resolves.
"""

from pathlib import Path

import pytest

from paperkit.config import load_config

PAPERS = Path(__file__).resolve().parent / "papers"
NAMES = sorted(p.name for p in PAPERS.iterdir() if p.is_dir()) if PAPERS.is_dir() else []


def test_the_fixtures_are_there() -> None:
    assert NAMES == ["acmart", "ieee", "minimal", "warnings"]


@pytest.mark.parametrize("name", NAMES)
def test_each_fixture_config_loads(name: str) -> None:
    config = load_config(PAPERS / name / ".paperkit.toml")
    assert config.mains == ["paper"]
    assert (config.root / "paper.tex").is_file()
    for bib in [config.bib] if config.bib else []:
        assert (config.root / bib).is_file()


def test_the_warnings_fixture_still_trips_the_source_checks() -> None:
    # If someone tidies these files, the fixture stops testing anything.
    notes = (PAPERS / "warnings" / "content" / "notes.tex").read_bytes()
    assert any(b > 127 for b in notes), "the non-ASCII character is gone"
    assert not notes.endswith(b"\n"), "the missing final newline came back"
    body = (PAPERS / "warnings" / "content" / "body.tex").read_text()
    assert any(line.rstrip("\n").endswith(" ") for line in body.splitlines(keepends=True))
    assert "uncited" in (PAPERS / "warnings" / "refs.bib").read_text()
