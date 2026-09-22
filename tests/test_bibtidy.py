# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the bibtidy command and its sort setting."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from paperkit import cli
from paperkit.config import PaperkitConfig, load_config
from paperkit.profiles import BaseProfile, get_profile


def test_sort_defaults_to_true() -> None:
    assert PaperkitConfig().checks.bibtex_tidy.sort is True


def test_sorted_args_contain_the_reordering_flags() -> None:
    args = BaseProfile().bibtex_tidy_args()
    assert set(BaseProfile.SORT_ARGS) <= set(args)


def test_unsorted_args_drop_only_the_reordering_flags() -> None:
    profile = BaseProfile()
    sorted_args = profile.bibtex_tidy_args(sort=True)
    unsorted = profile.bibtex_tidy_args(sort=False)
    assert set(sorted_args) - set(unsorted) == set(BaseProfile.SORT_ARGS)
    assert "--curly" in unsorted


def test_config_reads_sort(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text(
        '[project]\nmain = "p"\n\n[checks]\nbibtex_tidy = { enabled = true, sort = false }\n',
    )
    cfg = load_config(cfg_path)
    assert cfg.checks.bibtex_tidy.sort is False
    assert set(get_profile(cfg).bibtex_tidy_args(sort=cfg.checks.bibtex_tidy.sort)).isdisjoint(
        BaseProfile.SORT_ARGS,
    )


def test_config_rejects_non_boolean_sort(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text('[project]\nmain = "p"\n\n[checks]\nbibtex_tidy = { sort = "yes" }\n')
    with pytest.raises(ValueError, match="true or false"):
        load_config(cfg_path)


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> tuple[object, list[bool]]:
    """Run the CLI with the host tidy stubbed; returns (result, recorded sort values)."""
    seen: list[bool] = []
    monkeypatch.setattr(cli, "_get_config", lambda ctx: PaperkitConfig())
    monkeypatch.setattr(
        cli,
        "_tidy_host",
        lambda config: seen.append(config.checks.bibtex_tidy.sort),
    )
    return CliRunner().invoke(cli.main, argv), seen


def test_bibtidy_sorts_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    result, seen = _run(monkeypatch, ["bibtidy", "--no-docker"])
    assert result.exit_code == 0
    assert seen == [True]


def test_bibtidy_no_sort_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    result, seen = _run(monkeypatch, ["bibtidy", "--no-docker", "--no-sort"])
    assert result.exit_code == 0
    assert seen == [False]


def test_tidy_is_a_deprecated_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    result, seen = _run(monkeypatch, ["tidy", "--no-docker", "--no-sort"])
    assert result.exit_code == 0
    assert seen == [False]
    assert "now 'paperkit bibtidy'" in result.output


def test_tidy_alias_is_hidden_from_help() -> None:
    output = CliRunner().invoke(cli.main, ["--help"]).output
    assert "bibtidy" in output
    assert "\n  tidy" not in output


def test_docker_invocation_passes_the_sort_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[str] = []
    monkeypatch.setattr(cli, "_get_config", lambda ctx: PaperkitConfig())
    import paperkit.docker as docker_mod

    monkeypatch.setattr(docker_mod, "build_image", lambda config, verbose=False: "img")
    monkeypatch.setattr(
        docker_mod,
        "run_in_docker",
        lambda config, command, verbose=False: commands.append(command) or 0,
    )
    assert CliRunner().invoke(cli.main, ["bibtidy", "--no-sort"]).exit_code == 0
    assert commands == ["paperkit bibtidy --no-docker --no-sort"]
    assert CliRunner().invoke(cli.main, ["bibtidy"]).exit_code == 0
    assert commands[-1] == "paperkit bibtidy --no-docker --sort"
