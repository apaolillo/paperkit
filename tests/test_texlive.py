# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the [texlive] config section and upstream TeX Live install steps."""

import datetime as dt
from pathlib import Path

import pytest

from paperkit import texlive
from paperkit.config import TexliveConfig, load_config, parse_texlive

PIN = "bcd7c79264e92665f16f38de0cbfecf7057ef4d328af87a0d5afd903a95ef341" + (
    "ac095b1220badf8d56d411082be3eff3a5e0812782eb69d4926b6198233b17e4"
)


# -- repository resolution ------------------------------------------------------


def test_repository_takes_precedence_over_everything() -> None:
    tl = parse_texlive(
        {
            "source": "upstream",
            "repository": "https://example.org/tlnet/",
            "snapshot": "2026-09-18",
        },
    )
    assert texlive.resolve_repository(tl) == "https://example.org/tlnet"


def test_snapshot_resolves_to_dated_archive() -> None:
    tl = parse_texlive({"source": "upstream", "snapshot": "2026-09-18"})
    assert texlive.resolve_repository(tl) == (
        "https://www.texlive.info/tlnet-archive/2026/09/18/tlnet"
    )


def test_year_resolves_to_historic_tlnet_final() -> None:
    tl = parse_texlive({"source": "upstream", "year": 2025})
    assert texlive.resolve_repository(tl) == (
        "https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/tlnet-final"
    )


def test_live_ctan_is_the_unpinned_fallback() -> None:
    tl = parse_texlive({"source": "upstream"})
    assert texlive.resolve_repository(tl) == texlive.LIVE_REPOSITORY
    assert not texlive.is_pinned(tl)


@pytest.mark.parametrize(
    "raw",
    [
        {"snapshot": "2026-09-18"},
        {"year": 2025},
        {"repository": "https://example.org/tlnet"},
    ],
)
def test_pinned_sources(raw: dict[str, object]) -> None:
    assert texlive.is_pinned(parse_texlive({"source": "upstream", **raw}))


# -- install-tl profile -----------------------------------------------------------


def test_profile_for_default_upstream_config() -> None:
    profile = texlive.install_profile(TexliveConfig(source="upstream"))
    lines = profile.splitlines()
    assert lines[0] == "selected_scheme scheme-small"
    assert f"TEXDIR {texlive.TEXDIR}" in lines
    assert "instopt_adjustpath 0" in lines
    assert "tlpdbopt_install_docfiles 0" in lines
    assert "tlpdbopt_install_srcfiles 0" in lines
    assert not any(line.startswith("collection-") for line in lines)
    assert profile.endswith("\n")


def test_profile_never_lists_collections() -> None:
    # install-tl would take them as the whole selection and drop the scheme's.
    tl = parse_texlive(
        {
            "source": "upstream",
            "scheme": "scheme-medium",
            "collections": ["mathscience", "latexextra"],
            "docs": True,
            "sources": True,
        },
    )
    lines = texlive.install_profile(tl).splitlines()
    assert lines[0] == "selected_scheme scheme-medium"
    assert not any(line.startswith("collection-") for line in lines)
    assert "tlpdbopt_install_docfiles 1" in lines
    assert "tlpdbopt_install_srcfiles 1" in lines


def test_tlmgr_packages_are_sorted_deduplicated_and_prefixed() -> None:
    tl = parse_texlive(
        {
            "source": "upstream",
            "collections": ["mathscience", "collection-latexextra", "mathscience"],
            "packages": ["minted", "acmart", "minted"],
        },
    )
    assert texlive.tlmgr_packages(tl) == [
        "collection-latexextra",
        "collection-mathscience",
        "acmart",
        "minted",
    ]


def test_install_commands_are_deterministic() -> None:
    raw = {"source": "upstream", "collections": ["pictures", "latexextra", "fontsextra"]}
    assert texlive.install_commands(parse_texlive(raw)) == texlive.install_commands(
        parse_texlive(dict(raw, collections=["fontsextra", "pictures", "latexextra"])),
    )


# -- install commands -------------------------------------------------------------


def test_install_commands_verify_pin_before_downloading() -> None:
    tl = parse_texlive({"source": "upstream", "snapshot": "2026-09-18", "tlpdb_sha512": PIN})
    cmds = texlive.install_commands(tl)
    pin_idx = next(i for i, c in enumerate(cmds) if "texlive.tlpdb.sha512" in c)
    download_idx = next(i for i, c in enumerate(cmds) if "install-tl-unx.tar.gz " in c)
    assert pin_idx < download_idx
    assert any(PIN in c and "exit 1" in c for c in cmds)


def test_install_commands_without_pin_skip_tlpdb_check() -> None:
    cmds = texlive.install_commands(parse_texlive({"source": "upstream", "snapshot": "2026-09-18"}))
    assert not any("texlive.tlpdb.sha512" in c for c in cmds)


def test_tlmgr_repository_is_pinned_to_install_repository() -> None:
    tl = parse_texlive({"source": "upstream", "snapshot": "2026-09-18"})
    repo = texlive.resolve_repository(tl)
    assert f"{texlive.BIN_DIR}/tlmgr option repository {repo}" in texlive.install_commands(tl)


def test_collections_and_packages_installed_with_tlmgr_after_scheme() -> None:
    tl = parse_texlive(
        {"source": "upstream", "collections": ["latexextra"], "packages": ["minted"]},
    )
    cmds = texlive.install_commands(tl)
    tlmgr_install = f"{texlive.BIN_DIR}/tlmgr install collection-latexextra minted"
    assert tlmgr_install in cmds
    install_tl_idx = next(i for i, c in enumerate(cmds) if c.startswith("perl install-tl/"))
    assert install_tl_idx < cmds.index(tlmgr_install)


def test_no_tlmgr_install_without_collections_or_packages() -> None:
    cmds = texlive.install_commands(parse_texlive({"source": "upstream"}))
    assert not any(" install " in c and "tlmgr" in c for c in cmds)


# -- config validation --------------------------------------------------------------


def test_defaults_keep_distro_source() -> None:
    tl = parse_texlive({})
    assert tl == TexliveConfig()
    assert tl.source == "distro"


def test_toml_date_snapshot_is_accepted() -> None:
    tl = parse_texlive({"source": "upstream", "snapshot": dt.date(2026, 9, 18)})
    assert tl.snapshot == "2026-09-18"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"source": "ctan"}, "source"),
        ({"snapshot": "2026/09/18"}, "YYYY-MM-DD"),
        ({"snapshot": "2026-02-30"}, "not a valid date"),
        ({"snapshot": "2026-09-18", "year": 2025}, "mutually exclusive"),
        ({"year": "2025"}, "year"),
        ({"year": 2001}, "year"),
        ({"year": True}, "year"),
        ({"scheme": "huge"}, "unknown scheme"),
        ({"collections": "latexextra"}, "list of strings"),
        ({"collections": ["latex extra"]}, "invalid name"),
        ({"collections": ["science"]}, "'mathscience'"),
        ({"collections": ["latex-extra"]}, "'latexextra'"),
        ({"packages": ["minted; rm -rf /"]}, "invalid name"),
        ({"tlpdb_sha512": "abc"}, "128 hex"),
        ({"repository": "/local/tlnet"}, "URL"),
        ({"docs": "no"}, "true or false"),
        ({"snapshots": "2026-09-18"}, "unknown key"),
    ],
)
def test_invalid_config_is_rejected(raw: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_texlive(raw)


def test_load_config_reads_texlive_section(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text(
        '[project]\nmain = "paper"\n\n'
        '[texlive]\nsource = "upstream"\nsnapshot = 2026-09-18\n'
        'collections = ["latexextra"]\n',
    )
    cfg = load_config(cfg_path)
    assert cfg.texlive.source == "upstream"
    assert cfg.texlive.snapshot == "2026-09-18"
    assert cfg.texlive.collections == ["latexextra"]


def test_load_config_without_texlive_section_is_distro(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text('[project]\nmain = "paper"\n')
    assert load_config(cfg_path).texlive == TexliveConfig()
