# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the Typst pins, install steps and the [typst] config table."""

from pathlib import Path

import pytest

from paperkit import typst
from paperkit.config import load_config, parse_typst
from paperkit.typst import TypstConfig


def test_the_default_version_has_a_checksum_per_architecture() -> None:
    for arch in ("x86_64", "aarch64"):
        assert len(typst.KNOWN_GOOD_SHA256[arch]) == 64
        assert typst.expected_sha256(TypstConfig(), arch) == typst.KNOWN_GOOD_SHA256[arch]


def test_another_version_needs_its_own_checksum() -> None:
    with pytest.raises(ValueError, match="no known checksum for typst 0.9.0 on x86_64"):
        typst.expected_sha256(TypstConfig(version="0.9.0"), "x86_64")
    tc = TypstConfig(version="0.9.0", sha256="ab" * 32)
    assert typst.expected_sha256(tc, "x86_64") == "ab" * 32


def test_binary_install_downloads_verifies_and_installs() -> None:
    steps = typst.install_commands(TypstConfig(), "x86_64")
    assert steps[0].startswith("curl -fsSL -o /tmp/typst.tar.xz ")
    assert "typst-x86_64-unknown-linux-musl.tar.xz" in steps[0]
    assert f"v{typst.KNOWN_GOOD_VERSION}" in steps[0]
    assert steps[1].startswith(f'echo "{typst.KNOWN_GOOD_SHA256["x86_64"]}  /tmp/typst.tar.xz"')
    assert "sha256sum -c" in steps[1]
    assert any(s.startswith("install -m 0755 ") and s.endswith("/typst") for s in steps)
    assert steps[-1] == "typst --version"


def test_source_build_pins_the_tag_and_needs_no_checksum() -> None:
    steps = typst.install_commands(TypstConfig(version="0.9.0", build_from_source=True), "x86_64")
    assert steps[0] == (
        "cargo install --locked --git https://github.com/typst/typst --tag v0.9.0 typst-cli"
    )
    assert not any("sha256" in s for s in steps)


def test_packages_are_fetched_by_importing_them() -> None:
    assert typst.predownload_commands([]) == []
    steps = typst.predownload_commands(["@preview/charged-ieee:0.1.4", "@preview/cetz:0.3.4"])
    assert any("#import @preview/charged-ieee:0.1.4" in s for s in steps)
    assert any("typst compile /tmp/predownload.typ" in s for s in steps)
    assert any(typst.PACKAGE_CACHE_PATH in s for s in steps)


@pytest.mark.parametrize(
    ("spec", "namespace", "name", "version"),
    [
        ("@preview/charged-ieee:0.1.4", "preview", "charged-ieee", "0.1.4"),
        ("@spells/deliverable:2.0.0", "spells", "deliverable", "2.0.0"),
    ],
)
def test_package_specs_parse_as_imported(
    spec: str,
    namespace: str,
    name: str,
    version: str,
) -> None:
    p = typst.parse_package(spec)
    assert (p.namespace, p.name, p.version) == (namespace, name, version)
    assert p.spec == spec


@pytest.mark.parametrize(
    "spec",
    ["charged-ieee", "@preview/charged-ieee", "@preview/charged-ieee:latest", "preview/x:1.0.0"],
)
def test_bad_package_specs_are_rejected(spec: str) -> None:
    with pytest.raises(ValueError, match=r"\[typst\] packages"):
        typst.parse_package(spec)


def test_banner_and_mismatch() -> None:
    assert typst.parse_banner("typst 0.15.1 (9dfd3a08)") == "0.15.1"
    assert typst.parse_banner("typst 0.14.1 (unknown hash)") == "0.14.1"
    assert typst.parse_banner("This is pdfTeX, Version 3.14") is None
    assert typst.toolchain_mismatch(TypstConfig(), "0.15.1") is None
    mismatch = typst.toolchain_mismatch(TypstConfig(), "0.14.1")
    assert mismatch == "built with typst 0.14.1; config expects 0.15.1"


# -- the config table ------------------------------------------------------------------


def test_defaults_are_the_pinned_release_with_explicit_fonts() -> None:
    tc = parse_typst({})
    assert tc.version == typst.KNOWN_GOOD_VERSION
    assert tc.sha256 is None
    assert tc.ignore_system_fonts is True
    assert tc.fonts == [] and tc.packages == [] and tc.extra_args == []
    assert tc.packages_dir is None and tc.pdf_standard is None


def test_every_key_is_read() -> None:
    tc = parse_typst(
        {
            "version": "0.14.2",
            "sha256": "cd" * 32,
            "build_from_source": True,
            "fonts": ["fonts"],
            "ignore_system_fonts": False,
            "packages": ["@preview/charged-ieee:0.1.4"],
            "packages_dir": "~/.local/share/typst/packages",
            "pdf_standard": "a-2b",
            "extra_args": ["--pdf-tags", "false"],
        },
    )
    assert (tc.version, tc.sha256, tc.build_from_source) == ("0.14.2", "cd" * 32, True)
    assert (tc.fonts, tc.ignore_system_fonts) == (["fonts"], False)
    assert tc.packages == ["@preview/charged-ieee:0.1.4"]
    assert (tc.packages_dir, tc.pdf_standard) == ("~/.local/share/typst/packages", "a-2b")
    assert tc.extra_args == ["--pdf-tags", "false"]


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ({"verison": "0.15.1"}, "unknown key"),
        ({"version": "0.15"}, "version"),
        ({"sha256": "nope"}, "sha256"),
        ({"ignore_system_fonts": "no"}, "ignore_system_fonts"),
        ({"fonts": "fonts"}, "fonts"),
        ({"packages": ["charged-ieee"]}, "packages"),
        ({"pdf_standard": ""}, "pdf_standard"),
    ],
)
def test_bad_values_are_rejected(raw: dict[str, object], fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        parse_typst(raw)


def test_engine_typst_selects_typ_sources(tmp_path: Path) -> None:
    path = tmp_path / ".paperkit.toml"
    path.write_text(
        '[project]\nmain = "paper"\n[build]\nengine = "typst"\n[profile]\nname = "base"\n',
    )
    cfg = load_config(path)
    assert cfg.is_typst and cfg.main_suffix == ".typ"
    assert cfg.main_file("paper") == tmp_path.resolve() / "paper.typ"
    assert cfg.typst.version == typst.KNOWN_GOOD_VERSION


def test_latex_engines_keep_tex_sources(tmp_path: Path) -> None:
    path = tmp_path / ".paperkit.toml"
    path.write_text("")
    cfg = load_config(path)
    assert not cfg.is_typst and cfg.main_suffix == ".tex"


def test_an_unknown_engine_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / ".paperkit.toml"
    path.write_text('[build]\nengine = "tectonic"\n')
    with pytest.raises(ValueError, match=r"\[build\] engine: expected one of"):
        load_config(path)
