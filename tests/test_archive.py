# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the submission archive, including the compiled bibliography."""

import os
import time
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from paperkit import archive, cli
from paperkit.config import PaperkitConfig, load_config

BBL = "\\begin{thebibliography}{1}\n\\bibitem{a} An author.\n\\end{thebibliography}\n"


def _project(tmp_path: Path, mains: list[str], include: list[str] | None = None) -> PaperkitConfig:
    """A project with a .tex and a built .bbl per main, plus a bib file."""
    for main in mains:
        (tmp_path / f"{main}.tex").write_text(f"% {main}\n\\cite{{a}}\n")
        out = tmp_path / "out" / main
        out.mkdir(parents=True)
        (out / f"{main}.bbl").write_text(BBL)
    (tmp_path / "refs.bib").write_text("@misc{a, title={A}}\n")
    cfg = PaperkitConfig(root=tmp_path, main=mains[0], mains=list(mains), bib="refs.bib")
    cfg.zip.name = mains[0]
    cfg.zip.include = include if include is not None else ["{main}.tex", "refs.bib"]
    return cfg


def _names(result: archive.ZipResult) -> list[str]:
    with zipfile.ZipFile(result.path) as zf:
        return sorted(zf.namelist())


def _age(path: Path, seconds: float) -> None:
    """Backdate a file by *seconds*."""
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def test_without_the_setting_no_bbl_is_added(tmp_path: Path) -> None:
    result = archive.create_zip(_project(tmp_path, ["paper"]))
    assert _names(result) == ["paper.tex", "refs.bib"]
    assert result.warnings == []


def test_include_bbl_puts_it_next_to_the_tex(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    cfg.zip.include_bbl = True
    result = archive.create_zip(cfg)
    assert _names(result) == ["paper.bbl", "paper.tex", "refs.bib"]
    with zipfile.ZipFile(result.path) as zf:
        assert zf.read("paper.bbl").decode() == BBL
    assert result.warnings == []


def test_default_exclude_does_not_drop_the_requested_bbl(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    cfg.zip.include_bbl = True
    assert "*.bbl" in cfg.zip.exclude  # the default exclude list
    assert "paper.bbl" in _names(archive.create_zip(cfg))


def test_only_mains_in_the_archive_contribute_their_bbl(tmp_path: Path) -> None:
    # Two mains, but only one .tex is part of the archive.
    cfg = _project(tmp_path, ["paper", "report"], include=["paper.tex", "refs.bib"])
    cfg.zip.include_bbl = True
    assert _names(archive.create_zip(cfg)) == ["paper.bbl", "paper.tex", "refs.bib"]


def test_every_included_main_contributes_its_bbl(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper", "report"])
    cfg.zip.include_bbl = True
    assert _names(archive.create_zip(cfg)) == [
        "paper.bbl",
        "paper.tex",
        "refs.bib",
        "report.bbl",
        "report.tex",
    ]


def test_missing_bbl_is_an_error_and_keeps_the_previous_archive(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    cfg.zip.include_bbl = True
    previous = archive.create_zip(cfg).path
    before = previous.read_bytes()
    (tmp_path / "out" / "paper" / "paper.bbl").unlink()

    with pytest.raises(archive.MissingBblError, match="run `paperkit build` first"):
        archive.create_zip(cfg)
    assert previous.read_bytes() == before


def test_stale_bbl_warns_about_the_bib_and_the_tex(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    cfg.zip.include_bbl = True
    _age(tmp_path / "out" / "paper" / "paper.bbl", 120)
    result = archive.create_zip(cfg)
    assert "paper.bbl" in _names(result)  # warned about, still included
    assert len(result.warnings) == 2
    assert any("refs.bib" in w for w in result.warnings)
    assert any("paper.tex" in w for w in result.warnings)
    assert all("rebuild with `paperkit build`" in w for w in result.warnings)


def test_fresh_bbl_does_not_warn(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    cfg.zip.include_bbl = True
    _age(tmp_path / "paper.tex", 120)
    _age(tmp_path / "refs.bib", 120)
    assert archive.create_zip(cfg).warnings == []


# -- config and CLI ------------------------------------------------------------------


def test_config_reads_include_bbl(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text('[project]\nmain = "p"\n\n[zip]\ninclude_bbl = true\n')
    assert load_config(cfg_path).zip.include_bbl is True


def test_config_defaults_to_false_and_rejects_non_boolean(tmp_path: Path) -> None:
    assert PaperkitConfig().zip.include_bbl is False
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text('[project]\nmain = "p"\n\n[zip]\ninclude_bbl = "yes"\n')
    with pytest.raises(ValueError, match="include_bbl"):
        load_config(cfg_path)


@pytest.mark.parametrize(
    ("flag", "configured", "expect_bbl"),
    [
        ("--bbl", False, True),  # the flag overrides the config
        ("--no-bbl", True, False),
        (None, True, True),  # no flag: the config decides
        (None, False, False),
    ],
)
def test_cli_flag_overrides_the_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag: str | None,
    configured: bool,
    expect_bbl: bool,
) -> None:
    cfg = _project(tmp_path, ["paper"])
    cfg.zip.include_bbl = configured
    monkeypatch.setattr(cli, "_get_config", lambda ctx: cfg)
    result = CliRunner().invoke(cli.main, ["zip", *([flag] if flag else [])])
    assert result.exit_code == 0, result.output
    with zipfile.ZipFile(tmp_path / "paper-sources.zip") as zf:
        assert ("paper.bbl" in zf.namelist()) is expect_bbl


def test_cli_reports_the_missing_bbl_and_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _project(tmp_path, ["paper"])
    (tmp_path / "out" / "paper" / "paper.bbl").unlink()
    monkeypatch.setattr(cli, "_get_config", lambda ctx: cfg)
    result = CliRunner().invoke(cli.main, ["zip", "--bbl"])
    assert result.exit_code == 1
    assert "run `paperkit build` first" in result.output


def test_cli_shows_the_staleness_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _project(tmp_path, ["paper"])
    _age(tmp_path / "out" / "paper" / "paper.bbl", 120)
    monkeypatch.setattr(cli, "_get_config", lambda ctx: cfg)
    result = CliRunner().invoke(cli.main, ["zip", "--bbl"])
    assert result.exit_code == 0
    assert "warning:" in result.output
    assert "paper.bbl" in result.output  # also listed in the summary
