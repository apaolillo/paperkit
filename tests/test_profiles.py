# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the profile registry and what a profile contributes."""

import pytest

from paperkit import profiles
from paperkit.config import PaperkitConfig
from paperkit.profiles import BaseProfile, get_profile, register_profile
from paperkit.profiles.acm import ACMProfile


def _config(name: str) -> PaperkitConfig:
    cfg = PaperkitConfig()
    cfg.profile_name = name
    return cfg


def test_the_built_in_profiles_resolve_to_their_classes() -> None:
    assert type(get_profile(_config("base"))) is BaseProfile
    assert type(get_profile(_config("acm"))) is ACMProfile


def test_an_unknown_profile_is_an_error_not_a_fallback() -> None:
    with pytest.raises(ValueError, match=r"unknown profile 'amc' \(expected one of: acm, base\)"):
        get_profile(_config("amc"))


def test_a_registered_profile_is_found(monkeypatch: pytest.MonkeyPatch) -> None:
    class Mine(BaseProfile):
        pass

    monkeypatch.setitem(profiles._PROFILES, "mine", Mine)  # restored after the test
    assert type(get_profile(_config("mine"))) is Mine


def test_register_profile_adds_to_the_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profiles, "_PROFILES", dict(profiles._PROFILES))
    register_profile("x", ACMProfile)
    assert type(get_profile(_config("x"))) is ACMProfile


def test_acm_currently_adds_nothing_to_base() -> None:
    base, acm = BaseProfile(), ACMProfile()
    assert acm.docker_packages() == base.docker_packages() == []
    assert acm.bibtex_tidy_args() == base.bibtex_tidy_args()
    assert acm.bibtex_tidy_version() == base.bibtex_tidy_version() == "1.14.0"


def test_sorting_off_drops_exactly_the_reordering_arguments() -> None:
    with_sort = BaseProfile().bibtex_tidy_args(sort=True)
    without = BaseProfile().bibtex_tidy_args(sort=False)
    assert set(with_sort) - set(without) == set(BaseProfile.SORT_ARGS)
    assert [a for a in with_sort if a not in BaseProfile.SORT_ARGS] == without
    assert "--no-escape" in without  # the rest is untouched
