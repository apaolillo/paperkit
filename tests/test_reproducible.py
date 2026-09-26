# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for byte-reproducible builds (SOURCE_DATE_EPOCH and the trailer ID)."""

import datetime as dt
import shutil
import subprocess
from pathlib import Path

import pytest

from paperkit import builder, reproducible
from paperkit.config import PaperkitConfig, load_config

EPOCH = 1789898400  # 2026-09-20 10:00:00 UTC


@pytest.fixture(autouse=True)
def _no_inherited_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    """A SOURCE_DATE_EPOCH in the caller's environment would win over the config."""
    monkeypatch.delenv(reproducible.EPOCH_VAR, raising=False)


# -- the [build] setting -------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (EPOCH, EPOCH),
        ("git", "git"),
        ("2026-09-20", 1789862400),
        ("2026-09-20T10:00:00+00:00", EPOCH),
        (dt.date(2026, 9, 20), 1789862400),
        (dt.datetime(2026, 9, 20, 10, 0, tzinfo=dt.UTC), EPOCH),
    ],
)
def test_parse_setting(value: object, expected: int | str) -> None:
    assert reproducible.parse_setting(value) == expected


@pytest.mark.parametrize("value", ["yesterday", -1, True, 3.5])
def test_parse_setting_rejects_other_values(value: object) -> None:
    with pytest.raises(ValueError, match="source_date_epoch"):
        reproducible.parse_setting(value)


def test_config_reads_the_setting(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text(f'[project]\nmain = "p"\n\n[build]\nsource_date_epoch = {EPOCH}\n')
    assert load_config(cfg_path).source_date_epoch == EPOCH


def test_config_defaults_to_git() -> None:
    assert PaperkitConfig().source_date_epoch == "git"


# -- resolution ----------------------------------------------------------------------


def _git_repo(tmp_path: Path, epoch: int = EPOCH) -> Path:
    stamp = dt.datetime.fromtimestamp(epoch, dt.UTC).isoformat()
    env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    (tmp_path / "paper.tex").write_text("x\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.email=t@e",
            "-c",
            "user.name=T",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
        env={"PATH": "/usr/bin:/bin", **env, "HOME": str(tmp_path)},
    )
    return tmp_path


def test_environment_wins_over_the_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(reproducible.EPOCH_VAR, "12345")
    resolved = reproducible.resolve(EPOCH, Path("/nonexistent"))
    assert (resolved.epoch, resolved.source) == (12345, "environment")


def test_explicit_epoch_from_the_config() -> None:
    resolved = reproducible.resolve(EPOCH, Path("/nonexistent"))
    assert (resolved.epoch, resolved.source, resolved.warning) == (EPOCH, "config", None)


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_head_timestamp(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    resolved = reproducible.resolve("git", root)
    assert (resolved.epoch, resolved.source, resolved.warning) == (EPOCH, "git", None)


def test_without_git_it_warns_and_uses_now(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reproducible, "git_epoch", lambda _root: None)
    resolved = reproducible.resolve("git", tmp_path)
    assert resolved.source == "current time"
    assert resolved.warning is not None and "not be byte-identical" in resolved.warning


def test_source_date_renders_readably() -> None:
    assert str(reproducible.SourceDate(EPOCH, "git")).startswith(
        f"{EPOCH} (2026-09-20 10:00:00 UTC, from git)"
    )


def test_build_env_sets_both_variables() -> None:
    env = reproducible.build_env(reproducible.SourceDate(EPOCH, "git"))
    assert env == {"SOURCE_DATE_EPOCH": str(EPOCH), "FORCE_SOURCE_DATE": "1"}


# -- trailer id ----------------------------------------------------------------------


def test_trailer_id_is_deterministic_and_per_main() -> None:
    date = reproducible.SourceDate(EPOCH, "git")
    first = reproducible.trailer_id(date, "paper")
    assert first == reproducible.trailer_id(date, "paper")
    assert first != reproducible.trailer_id(date, "report")
    assert first != reproducible.trailer_id(reproducible.SourceDate(EPOCH + 1, "git"), "paper")
    assert len(first) == 32
    int(first, 16)


@pytest.mark.parametrize(
    ("engine", "year", "expected"),
    [
        ("pdflatex", 2026, True),  # pdfTeX needs it whatever the release
        ("xelatex", 2023, True),
        ("xelatex", 2024, False),  # xdvipdfmx derives it from the epoch
        ("xelatex", None, True),  # unknown release: pin to be safe
        ("lualatex", 2026, False),
    ],
)
def test_needs_trailer_id(
    engine: str, year: int | None, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reproducible, "texlive_year", lambda _engine: year)
    assert reproducible.needs_trailer_id(engine) is expected


def test_trailer_id_code_per_engine() -> None:
    date = reproducible.SourceDate(EPOCH, "git")
    pdf_id = reproducible.trailer_id(date, "paper")
    assert reproducible.trailer_id_code("pdflatex", date, "paper") == f"\\pdftrailerid{{{pdf_id}}}"
    assert "pdfvariable trailerid" in reproducible.trailer_id_code("lualatex", date, "paper")
    xetex = reproducible.trailer_id_code("xelatex", date, "paper")
    assert xetex.startswith("\\AtBeginDocument{\\special{pdf:trailerid [<")


# -- end to end ----------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="needs pdflatex")
def test_two_builds_produce_identical_bytes(tmp_path: Path) -> None:
    (tmp_path / "paper.tex").write_text(
        "\\documentclass{article}\n\\title{Repro}\n\\author{A}\n"
        "\\begin{document}\\maketitle Hello.\\end{document}\n",
    )
    cfg = PaperkitConfig(root=tmp_path, main="paper", mains=["paper"])
    cfg.passes, cfg.bibtex, cfg.shell_escape = 1, False, False
    cfg.source_date_epoch = EPOCH

    first = builder.build_paper(cfg, "paper")
    assert first.pdf is not None
    original = first.pdf.read_bytes()
    second = builder.build_paper(cfg, "paper")
    assert second.pdf is not None
    assert second.pdf.read_bytes() == original
