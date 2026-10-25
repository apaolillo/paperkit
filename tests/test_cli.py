# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the command-line entry point itself."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from paperkit import __version__, cli
from paperkit.config import load_config


def test_version_flag_reports_the_package_version() -> None:
    result = CliRunner().invoke(cli.main, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"paperkit, version {__version__}"


def test_short_version_flag_agrees() -> None:
    runner = CliRunner()
    assert runner.invoke(cli.main, ["-V"]).output == runner.invoke(cli.main, ["--version"]).output


def test_no_arguments_shows_the_help() -> None:
    result = CliRunner().invoke(cli.main, [], prog_name="paperkit")
    assert "Usage: paperkit" in result.output
    assert "texlive-update" in result.output


def test_init_writes_the_profile_defaults_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.main, ["init", "--profile", "ieee", "--texlive", "distro"])
    assert result.exit_code == 0, result.output
    text = (tmp_path / ".paperkit.toml").read_text()
    assert '"IEEEtran.cls",' in text and '"IEEEtran.bst",' in text
    assert "include_bbl = true" in text
    assert "passes = 3" in text
    assert 'name = "ieee"' in text
    # And what it wrote is what the loader reads back.
    cfg = load_config(tmp_path / ".paperkit.toml")
    assert cfg.profile_name == "ieee"
    assert cfg.zip.include[-1] == "IEEEtran.bst"


def test_init_renders_acm_differently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(cli.main, ["init", "--texlive", "distro"])  # acm is the default
    text = (tmp_path / ".paperkit.toml").read_text()
    assert "passes = 4" in text
    assert '"acmart.cls",' in text
    assert "# ack_counts_as_content = true" in text


def test_init_rejects_an_unknown_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.main, ["init", "--profile", "amc"])
    assert result.exit_code == 2
    assert all(n in result.output for n in ("acm", "ieee", "lncs", "usenix"))
    assert not (tmp_path / ".paperkit.toml").exists()


def test_init_typst_writes_a_typst_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.main, ["init", "--typst", "--profile", "ieee"])
    assert result.exit_code == 0, result.output
    text = (tmp_path / ".paperkit.toml").read_text()
    assert 'engine = "typst"' in text
    assert 'name = "typst-ieee"' in text
    assert "ignore_system_fonts = true" in text
    assert '"{main}.typ",' in text
    cfg = load_config(tmp_path / ".paperkit.toml")
    assert cfg.is_typst and cfg.profile_name == "typst-ieee"
    assert cfg.zip.include_bbl is False


def test_init_typst_defaults_to_the_acm_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(cli.main, ["init", "--typst"])
    assert 'name = "typst-acm"' in (tmp_path / ".paperkit.toml").read_text()
