# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the profile registry and what a profile contributes."""

from dataclasses import fields
from pathlib import Path

import pytest

from paperkit import archive, profiles
from paperkit.config import (
    ChecksConfig,
    PageLimitsConfig,
    PaperkitConfig,
    TexliveConfig,
    ZipConfig,
    load_config,
)
from paperkit.profiles import BaseProfile, get_profile, profile_names, register_profile
from paperkit.profiles.acm import ACMProfile
from paperkit.profiles.ieee import IEEEProfile
from paperkit.profiles.lncs import LNCSProfile
from paperkit.profiles.usenix import USENIXProfile


def test_the_built_in_profiles_resolve_to_their_classes() -> None:
    assert profile_names() == ["acm", "base", "ieee", "lncs", "usenix"]
    assert type(get_profile("base")) is BaseProfile
    assert type(get_profile("acm")) is ACMProfile
    assert type(get_profile("ieee")) is IEEEProfile
    assert type(get_profile("lncs")) is LNCSProfile
    assert type(get_profile("usenix")) is USENIXProfile


def test_an_unknown_profile_is_an_error_not_a_fallback() -> None:
    expected = r"unknown profile 'amc' \(expected one of: acm, base, ieee, lncs, usenix\)"
    with pytest.raises(ValueError, match=expected):
        get_profile("amc")


def test_register_profile_adds_to_the_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profiles, "_PROFILES", dict(profiles._PROFILES))

    class Mine(BaseProfile):
        pass

    register_profile("mine", Mine)
    assert type(get_profile("mine")) is Mine
    assert "mine" in profile_names()


# -- what the profiles set -------------------------------------------------------------

_SECTION_CLASSES = {
    "project": PaperkitConfig,
    "build": PaperkitConfig,
    "docker": PaperkitConfig,
    "texlive": TexliveConfig,
    "checks": ChecksConfig,
    "page_limits": PageLimitsConfig,
    "zip": ZipConfig,
}


@pytest.mark.parametrize("name", ["base", "acm", "ieee", "lncs", "usenix"])
def test_every_default_names_a_real_config_key(name: str) -> None:
    # A profile default for a key the loader does not know would be silently
    # ignored, which is worse than no default at all.
    for section, keys in get_profile(name).defaults().items():
        known = {f.name for f in fields(_SECTION_CLASSES[section])}
        assert set(keys) <= known, f"{name}: [{section}] {set(keys) - known}"


def test_base_ships_sources_and_bibliographies() -> None:
    assert get_profile("base").defaults() == {
        "zip": {"include": ["{main}.tex", "content/**/*.tex", "**/*.bib", "*.sty"]},
    }


def test_acm_adds_its_class_files_bbl_pbalance_pass_and_ack_rule() -> None:
    d = get_profile("acm").defaults()
    assert d["zip"]["include"][-2:] == ["acmart.cls", "ACM-Reference-Format.bst"]
    assert d["zip"]["include_bbl"] is True
    assert d["build"] == {"passes": 4}
    assert d["page_limits"] == {"ack_counts_as_content": True}


def test_ieee_adds_its_class_files_and_bbl() -> None:
    d = get_profile("ieee").defaults()
    assert d["zip"]["include"][-2:] == ["IEEEtran.cls", "IEEEtran.bst"]
    assert d["zip"]["include_bbl"] is True
    assert "build" not in d and "page_limits" not in d


def test_lncs_adds_its_class_files_and_bbl() -> None:
    d = get_profile("lncs").defaults()
    assert d["zip"]["include"][-2:] == ["llncs.cls", "splncs04.bst"]
    assert d["zip"]["include_bbl"] is True
    assert "build" not in d and "page_limits" not in d


def test_usenix_only_counts_the_acknowledgments() -> None:
    # Submission is a PDF and the style ships with the template, so the one
    # thing the profile knows is how USENIX counts pages.
    d = get_profile("usenix").defaults()
    assert d["page_limits"] == {"ack_counts_as_content": True}
    assert d["zip"] == get_profile("base").defaults()["zip"]
    assert "build" not in d


def test_profiles_do_not_share_their_lists() -> None:
    # Each defaults() call builds fresh lists: an append in one profile, or by
    # a caller, must not leak into another.
    get_profile("acm").defaults()["zip"]["include"].append("leak")
    assert "leak" not in get_profile("base").defaults()["zip"]["include"]
    assert "leak" not in get_profile("acm").defaults()["zip"]["include"]


def test_acm_and_ieee_build_on_base_for_everything_else() -> None:
    base = BaseProfile()
    for cls in (ACMProfile, IEEEProfile, LNCSProfile, USENIXProfile):
        p = cls()
        assert p.docker_packages() == base.docker_packages() == []
        assert p.bibtex_tidy_args() == base.bibtex_tidy_args()
        assert p.bibtex_tidy_version() == base.bibtex_tidy_version() == "1.14.0"


def test_sorting_off_drops_exactly_the_reordering_arguments() -> None:
    with_sort = BaseProfile().bibtex_tidy_args(sort=True)
    without = BaseProfile().bibtex_tidy_args(sort=False)
    assert set(with_sort) - set(without) == set(BaseProfile.SORT_ARGS)
    assert [a for a in with_sort if a not in BaseProfile.SORT_ARGS] == without
    assert "--no-escape" in without  # the rest is untouched


# -- defaults as a project sees them ---------------------------------------------------


def _load(tmp_path: Path, text: str) -> PaperkitConfig:
    path = tmp_path / ".paperkit.toml"
    path.write_text(text)
    return load_config(path)


def test_an_empty_file_gets_the_acm_defaults(tmp_path: Path) -> None:
    cfg = _load(tmp_path, "")
    assert cfg.profile_name == "acm"
    assert cfg.passes == 4
    assert cfg.zip.include_bbl is True
    assert cfg.page_limits.ack_counts_as_content is True
    assert cfg.zip.include[-1] == "ACM-Reference-Format.bst"


def test_the_file_wins_over_the_profile_key_by_key(tmp_path: Path) -> None:
    cfg = _load(tmp_path, '[build]\npasses = 3\n[zip]\ninclude = ["only.tex"]\n')
    assert cfg.passes == 3
    assert cfg.zip.include == ["only.tex"]  # the list is replaced, not merged
    assert cfg.zip.include_bbl is True  # a key the file leaves alone keeps its default


def test_the_base_profile_leaves_the_dataclass_defaults(tmp_path: Path) -> None:
    cfg = _load(tmp_path, '[profile]\nname = "base"\n')
    assert (cfg.passes, cfg.zip.include_bbl, cfg.page_limits.ack_counts_as_content) == (
        3,
        False,
        False,
    )


def test_profile_name_must_be_a_string(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\[profile\] name: expected a string"):
        _load(tmp_path, "[profile]\nname = 3\n")


def test_a_default_pattern_matching_no_file_is_harmless(tmp_path: Path) -> None:
    # The IEEE profile lists IEEEtran.cls; this project does not carry it.
    (tmp_path / "paper.tex").write_text("\\documentclass{IEEEtran}\n")
    (tmp_path / "refs.bib").write_text("@misc{a, title={A}}\n")
    cfg = _load(tmp_path, '[project]\nmain = "paper"\nbib = "refs.bib"\n[profile]\nname = "ieee"\n')
    result = archive.create_zip(cfg, include_bbl=False)
    import zipfile

    with zipfile.ZipFile(result.path) as zf:
        assert sorted(zf.namelist()) == ["paper.tex", "refs.bib"]
