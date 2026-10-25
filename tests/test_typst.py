# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the Typst pins, install steps and the [typst] config table."""

import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pythainer.builders import render_dockerfile_content

from paperkit import archive, bibliography, builder, checks, docker, typst
from paperkit.builder import BuildResult
from paperkit.checks import CheckStatus
from paperkit.config import PaperkitConfig, load_config, parse_typst
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
    assert any('#import "@preview/charged-ieee:0.1.4"' in s for s in steps)
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


# -- the build and the checks ----------------------------------------------------------


def _typst_project(tmp_path: Path, **typst_keys: object) -> PaperkitConfig:
    cfg = PaperkitConfig(root=tmp_path, main="paper", mains=["paper"], bib="refs.bib")
    cfg.engine = "typst"
    cfg.content_dirs = ["content"]
    for k, v in typst_keys.items():
        setattr(cfg.typst, k, v)
    (tmp_path / "paper.typ").write_text("= Hi\n")
    return cfg


def test_compile_command_carries_the_config(tmp_path: Path) -> None:
    cfg = _typst_project(
        tmp_path, fonts=["fonts"], pdf_standard="a-2b", extra_args=["--pdf-tags", "false"]
    )
    out = tmp_path / "out" / "paper"
    cmd = builder.typst_command(cfg, "paper", out)
    assert cmd[:2] == ["typst", "compile"]
    assert cmd[cmd.index("--root") + 1] == str(tmp_path)
    assert cmd[cmd.index("--deps") + 1] == str(out / "paper.deps")
    assert "--ignore-system-fonts" in cmd
    assert cmd[cmd.index("--font-path") + 1] == str(tmp_path / "fonts")
    assert cmd[cmd.index("--pdf-standard") + 1] == "a-2b"
    assert cmd[-4:-2] == ["--pdf-tags", "false"]
    assert cmd[-2:] == [str(tmp_path / "paper.typ"), str(out / "paper.pdf")]


def test_system_fonts_can_be_allowed(tmp_path: Path) -> None:
    cfg = _typst_project(tmp_path, ignore_system_fonts=False)
    assert "--ignore-system-fonts" not in builder.typst_command(cfg, "paper", tmp_path)


def test_run_typst_writes_a_log_behind_the_banner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _typst_project(tmp_path)
    out = tmp_path / "out" / "paper"
    out.mkdir(parents=True)

    def run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        if cmd[1] == "--version":
            return SimpleNamespace(stdout="typst 0.15.1 (9dfd3a08)\n", stderr="", returncode=0)
        return SimpleNamespace(
            stdout="", stderr="paper.typ:3:1: warning: unknown font family: Times\n", returncode=0
        )

    monkeypatch.setattr(subprocess, "run", run)
    assert builder.run_typst(cfg, "paper", out, {}) == 0
    log = (out / "paper.log").read_text().splitlines()
    assert log[0] == "typst 0.15.1 (9dfd3a08)"
    assert log[1].endswith("warning: unknown font family: Times")


def test_typst_log_check_counts_and_lists(tmp_path: Path) -> None:
    log = tmp_path / "paper.log"
    log.write_text(
        "typst 0.15.1 (9dfd3a08)\n"
        "paper.typ:3:1: warning: unknown font family: Times\n"
        "paper.typ:9:4: error: unknown variable: foo\n"
        "error: compilation failed\n",
    )
    result = checks.check_typst_log(log)
    assert result.status == CheckStatus.ERROR
    assert result.messages[0] == "2 error(s), 1 warning(s)"
    assert result.messages[1].strip().startswith("paper.typ:9:4: error")
    log.write_text("typst 0.15.1 (9dfd3a08)\npaper.typ:3:1: warning: unknown font family: Times\n")
    result = checks.check_typst_log(log)
    assert (result.status, result.messages[0]) == (CheckStatus.WARNING, "1 warning(s)")
    log.write_text("typst 0.15.1 (9dfd3a08)\n")
    assert checks.check_typst_log(log).messages == ["clean"]
    assert checks.check_typst_log(None).messages == []


def test_toolchain_check_against_the_pin(tmp_path: Path) -> None:
    cfg = _typst_project(tmp_path)
    log = tmp_path / "paper.log"
    log.write_text("typst 0.15.1 (9dfd3a08)\n")
    assert checks.check_toolchain(cfg, log).status == CheckStatus.CLEAN
    log.write_text("typst 0.14.1 (unknown hash)\nwarning: x\n")
    result = checks.check_toolchain(cfg, log)
    assert result.status == CheckStatus.WARNING
    assert "built with typst 0.14.1; config expects 0.15.1" in result.messages[0]
    assert checks.check_toolchain(cfg, None).status == CheckStatus.SKIPPED


def test_run_all_checks_picks_the_typst_set(tmp_path: Path) -> None:
    cfg = _typst_project(tmp_path)
    out = tmp_path / "out" / "paper"
    out.mkdir(parents=True)
    (out / "paper.log").write_text("typst 0.15.1 (9dfd3a08)\n")
    result = BuildResult(log=out / "paper.log", output_dir=out, success=True)
    names = [cr.name for cr in checks.run_all_checks(cfg, result)]
    assert names[:2] == ["Typst", "Toolchain"]
    assert "Boxes" not in names and "LaTeX" not in names and "BibTeX" not in names
    assert "Non-ASCII" in names and "Pages/Limit" in names


def test_sources_are_typ_files_for_typst(tmp_path: Path) -> None:
    cfg = _typst_project(tmp_path)
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "a.typ").write_text("x\n")
    (tmp_path / "content" / "old.tex").write_text("x\n")
    files = [f.name for f in checks._collect_source_files(cfg)]
    assert files == ["a.typ", "paper.typ"]
    assert checks.check_non_ascii(cfg).messages == ["All source .typ files are ASCII-clean"]


def test_citations_are_queried_from_typst(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _typst_project(tmp_path)
    (tmp_path / "refs.bib").write_text("@misc{a, title={A}}\n@misc{b, title={B}}\n")
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(cmd)
        if cmd[-2:] == ["--field", "key"]:
            return SimpleNamespace(stdout='["<a>", "<a>"]\n', returncode=0)
        if cmd[-2:] == ["--field", "target"]:
            return SimpleNamespace(stdout='["<fig:sun>", "<a>"]\n', returncode=0)
        return SimpleNamespace(stdout="[false]\n", returncode=0)

    monkeypatch.setattr(subprocess, "run", run)
    out = tmp_path / "out" / "paper"
    out.mkdir(parents=True)
    cites = bibliography.write_citations(cfg, "paper", out)
    assert cites == out / "paper.cites"
    assert json.loads(cites.read_text()) == {"citations": ["a", "fig:sun"], "cite_all": False}
    assert calls[0][:3] == ["typst", "query", "--root"]
    usage = bibliography.usage_from_dir(cfg, "paper", out, "this run")
    assert usage is not None
    assert (usage.citations, usage.cite_all) == ({"a", "fig:sun"}, False)
    assert usage.bib_files == {(tmp_path / "refs.bib").resolve()}
    # The whole check, end to end, sees b as unused.
    results = bibliography.project_bib_checks(
        cfg, {"paper": BuildResult(output_dir=out, success=True)}, focus=["paper"]
    )
    unused = next(r for r in results if r.name == "Unused bib entries")
    assert any(m.strip() == "b" for m in unused.messages)


def test_a_missing_typst_makes_the_query_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _typst_project(tmp_path)

    def run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        raise FileNotFoundError("typst")

    monkeypatch.setattr(subprocess, "run", run)
    assert bibliography.query_citations(cfg, "paper") is None
    assert bibliography.draft_usage(cfg, "paper") is None


def test_hayagriva_keys_are_the_top_level_ones(tmp_path: Path) -> None:
    yml = tmp_path / "refs.yml"
    yml.write_text(
        "harry:\n  type: Book\n  title: Harry Potter\nelectronic:\n  type: Web\n  url: x\n"
    )
    assert bibliography.bib_entry_keys(yml) == {"harry", "electronic"}


def test_bibtex_tidy_is_skipped_for_hayagriva(tmp_path: Path) -> None:
    cfg = _typst_project(tmp_path)
    cfg.bib = "refs.yml"
    result = checks.check_bibtex_tidy(cfg)
    assert (result.status, result.messages) == (
        CheckStatus.CLEAN,
        ["Skipped (Hayagriva bibliography, not BibTeX)"],
    )


# -- the image ----------------------------------------------------------------------------


def _dockerfile(cfg: PaperkitConfig) -> str:
    builder = docker.make_builder(cfg)
    return render_dockerfile_content(package_manager="apt", commands=builder._build_commands)


def test_a_typst_image_has_no_tex_live(tmp_path: Path) -> None:
    text = _dockerfile(_typst_project(tmp_path))
    assert "texlive" not in text.lower()
    assert "pandoc" not in text
    assert "poppler-utils" in text and "npm" in text
    assert (
        f"v{typst.KNOWN_GOOD_VERSION}/typst-{typst.host_arch()}-unknown-linux-musl.tar.xz" in text
    )
    assert "sha256sum -c" in text
    assert "typst --version" in text
    assert f"ENV TYPST_PACKAGE_PATH={typst.PACKAGE_PATH}" in text
    assert f"ENV TYPST_PACKAGE_CACHE_PATH={typst.PACKAGE_CACHE_PATH}" in text
    assert "ENV TYPST_FONT_PATHS=/usr/share/fonts:/usr/share/texmf/fonts" in text
    assert "rustup" not in text and "cargo" not in text
    assert "pip install --break-system-packages" in text  # paperkit itself


def test_declared_packages_are_fetched_into_the_image(tmp_path: Path) -> None:
    cfg = _typst_project(tmp_path, packages=["@preview/charged-ieee:0.1.4"])
    text = _dockerfile(cfg)
    assert '#import "@preview/charged-ieee:0.1.4"' in text
    assert "typst compile /tmp/predownload.typ" in text
    # The compiler layer comes before the packages layer, so a package change
    # does not reinstall the compiler.
    assert text.index("sha256sum -c") < text.index("predownload")


def test_building_from_source_brings_a_rust_toolchain(tmp_path: Path) -> None:
    cfg = _typst_project(tmp_path, build_from_source=True, version="0.9.0")
    text = _dockerfile(cfg)
    assert "sh.rustup.rs" in text
    assert (
        "cargo install --locked --git https://github.com/typst/typst --tag v0.9.0 typst-cli" in text
    )
    assert "sha256sum" not in text


def test_a_latex_image_is_untouched(tmp_path: Path) -> None:
    text = _dockerfile(PaperkitConfig(root=tmp_path))
    assert "typst" not in text.lower()
    assert "texlive" in text.lower()


def test_local_packages_are_mounted_read_only(tmp_path: Path) -> None:
    pkgs = tmp_path / "pkgs"
    pkgs.mkdir()
    cfg = _typst_project(tmp_path, packages_dir=str(pkgs))
    volumes = docker.container_volumes(cfg)
    assert volumes[str(tmp_path)] == str(docker.CONTAINER_WORKDIR)
    assert volumes[str(pkgs.resolve())] == f"{typst.PACKAGE_PATH}:ro"


def test_a_missing_packages_dir_is_not_mounted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _typst_project(tmp_path, packages_dir=str(tmp_path / "nowhere"))
    volumes = docker.container_volumes(cfg)
    assert list(volumes) == [str(tmp_path)]
    assert "not a directory" in capsys.readouterr().out


def test_host_arch_maps_to_a_release_name(monkeypatch: pytest.MonkeyPatch) -> None:
    for machine, arch in (
        ("x86_64", "x86_64"),
        ("AMD64", "x86_64"),
        ("aarch64", "aarch64"),
        ("arm64", "aarch64"),
    ):
        monkeypatch.setattr(typst.platform, "machine", lambda m=machine: m)
        assert typst.host_arch() == arch
    monkeypatch.setattr(typst.platform, "machine", lambda: "riscv64")
    with pytest.raises(ValueError, match="riscv64"):
        typst.host_arch()


def test_packages_are_read_off_the_dependency_paths() -> None:
    inputs = [
        "paper.typ",
        "content/1.0.0/notes.typ",  # a project path that happens to look like a version
        "/opt/typst/cache/preview/charged-ieee/0.1.4/lib.typ",  # the image's cache
        "/opt/typst/cache/preview/charged-ieee/0.1.4/template/main.typ",
        "/opt/typst/packages/spells/deliverable/2.0.0/lib.typ",  # a mounted local namespace
        "/home/me/.cache/typst/packages/preview/cetz/0.3.4/lib.typ",  # a host cache
        "@preview/tablex:0.0.9/tablex.typ",  # the virtual form
    ]
    assert typst.packages_from_deps(inputs) == {
        "@preview/charged-ieee:0.1.4",
        "@spells/deliverable:2.0.0",
        "@preview/cetz:0.3.4",
        "@preview/tablex:0.0.9",
    }


def test_undeclared_universe_packages_are_a_warning(tmp_path: Path) -> None:
    cfg = _typst_project(tmp_path, packages=["@preview/cetz:0.3.4"])
    deps = tmp_path / "paper.deps"
    deps.write_text(
        json.dumps(
            {
                "inputs": [
                    "paper.typ",
                    "/opt/typst/cache/preview/charged-ieee/0.1.4/lib.typ",
                    "/opt/typst/cache/preview/cetz/0.3.4/lib.typ",
                    "/opt/typst/packages/spells/deliverable/2.0.0/lib.typ",  # local
                ]
            }
        )
    )
    result = checks.check_typst_packages(cfg, deps)
    assert result.status == CheckStatus.WARNING
    assert result.messages[0] == "1 package(s) downloaded at build time, not declared:"
    assert result.messages[1].strip() == "@preview/charged-ieee:0.1.4"
    cfg.typst.packages.append("@preview/charged-ieee:0.1.4")
    result = checks.check_typst_packages(cfg, deps)
    assert (result.status, result.messages) == (
        CheckStatus.CLEAN,
        ["3 package(s), all available in the image"],
    )
    deps.write_text(json.dumps({"inputs": ["paper.typ"]}))
    assert checks.check_typst_packages(cfg, deps).messages == ["No packages used"]
    assert checks.check_typst_packages(cfg, None).status == CheckStatus.SKIPPED


# -- the archive --------------------------------------------------------------------------


def _typst_archive_project(tmp_path: Path) -> PaperkitConfig:
    cfg = _typst_project(tmp_path)
    cfg.content_dirs = []
    cfg.zip.name = "paper"
    cfg.zip.include = ["{main}.typ"]
    (tmp_path / "used.typ").write_text("x\n")
    (tmp_path / "unused.typ").write_text("x\n")
    (tmp_path / "refs.bib").write_text("@misc{a, title={A}}\n")
    (tmp_path / "fonts").mkdir()
    (tmp_path / "fonts" / "Times.otf").write_bytes(b"font")
    cfg.typst.fonts = ["fonts"]
    return cfg


def test_the_archive_is_what_the_build_read_plus_the_fonts(tmp_path: Path) -> None:
    cfg = _typst_archive_project(tmp_path)
    out = tmp_path / "out" / "paper"
    out.mkdir(parents=True)
    (out / "paper.deps").write_text(
        json.dumps(
            {
                "inputs": [
                    "paper.typ",
                    "used.typ",
                    "refs.bib",
                    "/opt/typst/cache/preview/cetz/0.3.4/lib.typ",
                ]
            }
        )
    )
    result = archive.create_zip(cfg)
    with zipfile.ZipFile(result.path) as zf:
        assert sorted(zf.namelist()) == ["fonts/Times.otf", "paper.typ", "refs.bib", "used.typ"]
    assert result.warnings == []


def test_without_a_build_the_patterns_alone_are_archived_with_a_warning(tmp_path: Path) -> None:
    cfg = _typst_archive_project(tmp_path)
    result = archive.create_zip(cfg)
    with zipfile.ZipFile(result.path) as zf:
        assert sorted(zf.namelist()) == ["fonts/Times.otf", "paper.typ"]
    assert len(result.warnings) == 1 and "no dependency list" in result.warnings[0]


def test_include_bbl_is_ignored_for_typst_with_a_warning(tmp_path: Path) -> None:
    cfg = _typst_archive_project(tmp_path)
    cfg.zip.include_bbl = True
    result = archive.create_zip(cfg)
    assert any("include_bbl ignored" in w for w in result.warnings)


def test_the_ieee_profile_brings_its_fonts_into_the_image(tmp_path: Path) -> None:
    cfg = _typst_project(tmp_path)
    cfg.profile_name = "typst-ieee"
    assert "fonts-texgyre" in _dockerfile(cfg)
    cfg.profile_name = "typst-acm"
    assert "fonts-texgyre" not in _dockerfile(cfg)


def test_typst_projects_get_their_own_image_tag(tmp_path: Path) -> None:
    path = tmp_path / ".paperkit.toml"
    path.write_text('[build]\nengine = "typst"\n[profile]\nname = "typst"\n')
    assert load_config(path).image_name == "paperkit-typst-builder"
    path.write_text(
        '[build]\nengine = "typst"\n[docker]\nimage_name = "mine"\n[profile]\nname = "typst"\n'
    )
    assert load_config(path).image_name == "mine"
    path.write_text("")
    assert load_config(path).image_name == "paperkit-builder"
