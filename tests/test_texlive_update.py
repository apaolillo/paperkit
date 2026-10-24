# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the init defaults and `paperkit texlive-update`."""

import datetime as dt
from pathlib import Path

import pytest
from click.testing import CliRunner

from paperkit import cli, texlive
from paperkit.config import load_config

DIGEST = "a" * 128
OTHER = "b" * 128


def _init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Path:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.main, ["init", *args])
    assert result.exit_code == 0, result.output
    return tmp_path / ".paperkit.toml"


# -- init defaults -------------------------------------------------------------------


def test_init_pins_the_known_good_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(_init(tmp_path, monkeypatch))
    assert cfg.texlive.source == "upstream"
    assert cfg.texlive.snapshot == texlive.KNOWN_GOOD_SNAPSHOT
    assert cfg.texlive.tlpdb_sha512 == texlive.KNOWN_GOOD_TLPDB_SHA512
    assert cfg.texlive.scheme == texlive.DEFAULT_SCHEME
    assert cfg.texlive.collections == list(texlive.DEFAULT_COLLECTIONS)


def test_init_can_still_ask_for_the_distro_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = load_config(_init(tmp_path, monkeypatch, "--texlive", "distro"))
    assert cfg.texlive.source == "distro"
    assert cfg.texlive.snapshot is None


def test_the_known_good_snapshot_is_well_formed() -> None:
    dt.date.fromisoformat(texlive.KNOWN_GOOD_SNAPSHOT)
    assert texlive._SHA512_HEX.fullmatch(texlive.KNOWN_GOOD_TLPDB_SHA512)


# -- finding the newest snapshot -------------------------------------------------------


def test_latest_snapshot_walks_back_to_the_newest_published_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = {"2026-10-20": DIGEST}
    monkeypatch.setattr(texlive, "fetch_tlpdb_sha512", lambda s: published.get(s))
    assert texlive.latest_snapshot(dt.date(2026, 10, 22)) == ("2026-10-20", DIGEST)


def test_latest_snapshot_gives_up_after_the_lookback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(texlive, "fetch_tlpdb_sha512", lambda s: None)
    assert texlive.latest_snapshot(dt.date(2026, 10, 22)) is None


def test_snapshot_url() -> None:
    assert texlive.snapshot_url("2026-10-22").endswith("/tlnet-archive/2026/10/22/tlnet")


# -- rewriting the config ---------------------------------------------------------------

CONFIG = f"""[project]
main = "paper"

# A comment that must survive.
[texlive]
source = "upstream"
snapshot = "2026-01-01"
tlpdb_sha512 = "{OTHER}"
scheme = "small"
"""


def test_update_replaces_both_values_and_keeps_the_rest() -> None:
    new, previous = texlive.update_config_text(CONFIG, "2026-10-22", DIGEST)
    assert previous == {"snapshot": "2026-01-01", "tlpdb_sha512": OTHER}
    assert 'snapshot = "2026-10-22"' in new
    assert f'tlpdb_sha512 = "{DIGEST}"' in new
    assert "# A comment that must survive." in new
    assert 'scheme = "small"' in new


def test_update_adds_the_checksum_when_the_project_had_none() -> None:
    config = CONFIG.replace(f'tlpdb_sha512 = "{OTHER}"\n', "")
    new, previous = texlive.update_config_text(config, "2026-10-22", DIGEST)
    assert previous == {"snapshot": "2026-01-01"}
    assert f'tlpdb_sha512 = "{DIGEST}"' in new


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ('[project]\nmain = "p"\n', "no \\[texlive\\] section"),
        ('[texlive]\nsource = "distro"\n', "does not pin one"),
    ],
)
def test_update_refuses_what_it_cannot_change(config: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        texlive.update_config_text(config, "2026-10-22", DIGEST)


# -- the command -------------------------------------------------------------------------


def _project(tmp_path: Path) -> Path:
    path = tmp_path / ".paperkit.toml"
    path.write_text(CONFIG)
    return path


def _run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, newest: tuple[str, str] | None, *args: str
) -> tuple[int, str]:
    path = _project(tmp_path)
    monkeypatch.setattr(cli, "_config_path", lambda ctx: path)
    monkeypatch.setattr(texlive, "latest_snapshot", lambda: newest)
    result = CliRunner().invoke(cli.main, ["texlive-update", *args])
    return result.exit_code, result.output


def test_command_updates_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, output = _run(tmp_path, monkeypatch, ("2026-10-22", DIGEST))
    assert code == 0
    assert "2026-01-01 -> 2026-10-22" in output
    assert 'snapshot = "2026-10-22"' in (tmp_path / ".paperkit.toml").read_text()


def test_check_reports_without_editing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, output = _run(tmp_path, monkeypatch, ("2026-10-22", DIGEST), "--check")
    assert code == 0
    assert "not modified" in output
    assert (tmp_path / ".paperkit.toml").read_text() == CONFIG


def test_already_current_is_a_no_op(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, output = _run(tmp_path, monkeypatch, ("2026-01-01", OTHER))
    assert code == 0
    assert "already on the newest snapshot" in output
    assert (tmp_path / ".paperkit.toml").read_text() == CONFIG


def test_unreachable_archive_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, output = _run(tmp_path, monkeypatch, None)
    assert code == 1
    assert "no snapshot found" in output
