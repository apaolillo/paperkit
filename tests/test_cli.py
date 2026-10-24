# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the command-line entry point itself."""

from click.testing import CliRunner

from paperkit import __version__, cli


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
