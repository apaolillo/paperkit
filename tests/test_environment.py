"""Tests for build-environment reporting: log banners, toolchain checks, SKIPPED."""

from pathlib import Path

import pytest

from paperkit import checks, report, texlive
from paperkit.builder import BuildResult
from paperkit.checks import CheckResult, CheckStatus
from paperkit.config import PaperkitConfig, parse_texlive

# Real first log lines from TeX Live 2026 (upstream) and Debian's TeX Live 2022.
PDFTEX_2026 = (
    "This is pdfTeX, Version 3.141592653-2.6-1.40.29 (TeX Live 2026) "
    "(preloaded format=pdflatex 2026.9.19)  19 SEP 2026 14:16"
)
LUAHBTEX_2026 = (
    "This is LuaHBTeX, Version 1.24.0 (TeX Live 2026)  "
    "(format=lualatex 2026.9.19)  19 SEP 2026 14:16"
)
XETEX_2026 = (
    "This is XeTeX, Version 3.141592653-2.6-0.999998 (TeX Live 2026) "
    "(preloaded format=xelatex 2026.9.19)  19 SEP 2026 14:17"
)
PDFTEX_DEBIAN = (
    "This is pdfTeX, Version 3.141592653-2.6-1.40.22 (TeX Live 2022/dev/Debian) "
    "(preloaded format=pdflatex 2026.1.31)  19 SEP 2026 16:19"
)
LUAHBTEX_DEBIAN = (
    "This is LuaHBTeX, Version 1.14.0 (TeX Live 2022/dev/Debian)  "
    "(format=lualatex 2026.1.31)  19 SEP 2026 16:19"
)
XETEX_DEBIAN = (
    "This is XeTeX, Version 3.141592653-2.6-0.999993 (TeX Live 2022/dev/Debian) "
    "(preloaded format=xelatex 2026.1.31)  19 SEP 2026 16:19"
)


def _write_log(tmp_path: Path, first_line: str) -> Path:
    log = tmp_path / "paper.log"
    log.write_text(f"{first_line}\nentering extended mode\n restricted \\write18 enabled.\n")
    return log


def _upstream(**raw: object) -> PaperkitConfig:
    cfg = PaperkitConfig()
    cfg.texlive = parse_texlive({"source": "upstream", **raw})
    return cfg


# -- banner parsing ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "text", "year", "distro"),
    [
        (PDFTEX_2026, "pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026)", 2026, False),
        (LUAHBTEX_2026, "LuaHBTeX 1.24.0 (TeX Live 2026)", 2026, False),
        (XETEX_2026, "XeTeX 3.141592653-2.6-0.999998 (TeX Live 2026)", 2026, False),
        (
            PDFTEX_DEBIAN,
            "pdfTeX 3.141592653-2.6-1.40.22 (TeX Live 2022/dev/Debian)",
            2022,
            True,
        ),
        (LUAHBTEX_DEBIAN, "LuaHBTeX 1.14.0 (TeX Live 2022/dev/Debian)", 2022, True),
        (
            XETEX_DEBIAN,
            "XeTeX 3.141592653-2.6-0.999993 (TeX Live 2022/dev/Debian)",
            2022,
            True,
        ),
    ],
)
def test_parse_log_banner(line: str, text: str, year: int, distro: bool) -> None:
    banner = texlive.parse_log_banner(line)
    assert banner is not None
    assert str(banner) == text
    assert banner.year == year
    assert banner.is_distro_build is distro


@pytest.mark.parametrize("line", ["", "entering extended mode", "This is not a banner"])
def test_parse_log_banner_rejects_other_lines(line: str) -> None:
    assert texlive.parse_log_banner(line) is None


def test_read_log_banner_uses_first_line(tmp_path: Path) -> None:
    banner = texlive.read_log_banner(_write_log(tmp_path, XETEX_2026))
    assert banner is not None
    assert banner.engine == "XeTeX"


def test_read_log_banner_without_log(tmp_path: Path) -> None:
    assert texlive.read_log_banner(None) is None
    assert texlive.read_log_banner(tmp_path / "missing.log") is None


# -- toolchain mismatch -------------------------------------------------------------


def _banner(line: str) -> texlive.EngineBanner:
    banner = texlive.parse_log_banner(line)
    assert banner is not None
    return banner


def test_distro_config_never_mismatches() -> None:
    assert texlive.toolchain_mismatch(parse_texlive({}), _banner(PDFTEX_DEBIAN)) is None


@pytest.mark.parametrize(
    ("raw", "line"),
    [
        ({"snapshot": "2026-09-18"}, PDFTEX_2026),
        # Early-year snapshot still serving the previous release.
        ({"snapshot": "2027-01-15"}, PDFTEX_2026),
        ({"year": 2026}, LUAHBTEX_2026),
        ({"repository": "https://example.org/tlnet"}, XETEX_2026),
        ({}, PDFTEX_2026),
    ],
)
def test_matching_upstream_builds(raw: dict[str, object], line: str) -> None:
    tl = parse_texlive({"source": "upstream", **raw})
    assert texlive.toolchain_mismatch(tl, _banner(line)) is None


@pytest.mark.parametrize(
    ("raw", "line"),
    [
        # Host distro TeX Live used for an upstream config.
        ({"snapshot": "2026-09-18"}, PDFTEX_DEBIAN),
        ({"repository": "https://example.org/tlnet"}, XETEX_DEBIAN),
        ({}, LUAHBTEX_DEBIAN),
        # Wrong release.
        ({"year": 2025}, PDFTEX_2026),
        ({"snapshot": "2028-06-01"}, PDFTEX_2026),
    ],
)
def test_mismatching_builds(raw: dict[str, object], line: str) -> None:
    tl = parse_texlive({"source": "upstream", **raw})
    reason = texlive.toolchain_mismatch(tl, _banner(line))
    assert reason is not None
    assert _banner(line).distribution in reason


def test_check_toolchain_warns_on_mismatch(tmp_path: Path) -> None:
    cfg = _upstream(snapshot="2026-09-18")
    result = checks.check_toolchain(cfg, _write_log(tmp_path, PDFTEX_DEBIAN))
    assert result.status == CheckStatus.WARNING
    assert "TeX Live 2022/dev/Debian" in result.messages[0]
    assert "snapshot 2026-09-18" in result.messages[0]


def test_check_toolchain_clean_on_match(tmp_path: Path) -> None:
    cfg = _upstream(snapshot="2026-09-18")
    result = checks.check_toolchain(cfg, _write_log(tmp_path, PDFTEX_2026))
    assert result.status == CheckStatus.CLEAN
    assert result.messages == ["TeX Live 2026 (upstream, snapshot 2026-09-18)"]


def test_check_toolchain_skipped_without_log(tmp_path: Path) -> None:
    result = checks.check_toolchain(_upstream(snapshot="2026-09-18"), tmp_path / "none.log")
    assert result.status == CheckStatus.SKIPPED


def test_toolchain_check_only_for_upstream_configs(tmp_path: Path) -> None:
    log = _write_log(tmp_path, PDFTEX_DEBIAN)
    build = BuildResult(log=log, output_dir=tmp_path, success=True)
    names = {cr.name for cr in checks.run_all_checks(PaperkitConfig(root=tmp_path), build)}
    assert "Toolchain" not in names
    upstream = _upstream(snapshot="2026-09-18")
    upstream.root = tmp_path
    assert "Toolchain" in {cr.name for cr in checks.run_all_checks(upstream, build)}


# -- environment info ---------------------------------------------------------------


def test_environment_tex_line_comes_from_log(tmp_path: Path) -> None:
    build = BuildResult(log=_write_log(tmp_path, PDFTEX_2026), output_dir=tmp_path)
    info = report.get_environment_info(_upstream(snapshot="2026-09-18"), build)
    assert info["TeX Live"] == "pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026)"
    assert info["TeX Live source"] == "upstream, snapshot 2026-09-18"


def test_environment_falls_back_to_labelled_host_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / "bin" / "pdflatex"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\necho 'pdfTeX 3.14 (TeX Live 2099)'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake.parent))
    build = BuildResult(log=None, output_dir=tmp_path)
    info = report.get_environment_info(PaperkitConfig(), build)
    assert info["TeX Live"] == "pdfTeX 3.14 (TeX Live 2099) (host pdflatex, no build log)"


def test_environment_without_log_or_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    info = report.get_environment_info(PaperkitConfig(), BuildResult(output_dir=tmp_path))
    assert "TeX Live" not in info


# -- SKIPPED status -----------------------------------------------------------------


def test_missing_bibtex_tidy_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "refs.bib").write_text("@misc{a,title={A}}\n")
    cfg = PaperkitConfig(root=tmp_path, bib="refs.bib")
    monkeypatch.setattr(checks.shutil, "which", lambda _name: None)
    result = checks.check_bibtex_tidy(cfg)
    assert result.status == CheckStatus.SKIPPED
    assert "bibtex-tidy not found" in result.messages[0]


def test_missing_pdffonts_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    monkeypatch.setattr(checks.shutil, "which", lambda _name: None)
    assert checks.check_font_embedding(pdf).status == CheckStatus.SKIPPED


def test_skipped_counts_as_warning_in_verdict() -> None:
    results = [CheckResult(name="A"), CheckResult(name="B", status=CheckStatus.SKIPPED)]
    assert report._worst_status(results) == CheckStatus.WARNING
    advisory = [CheckResult(name="P", status=CheckStatus.SKIPPED, advisory=True)]
    assert report._worst_status(advisory) == CheckStatus.CLEAN


def test_skipped_row_renders_yellow(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    skipped = CheckResult(
        name="BibTeX tidy",
        status=CheckStatus.SKIPPED,
        messages=["Skipped (bibtex-tidy not found)"],
    )
    report.print_report(BuildResult(output_dir=tmp_path), [CheckResult(name="LaTeX"), skipped])
    out = capsys.readouterr().out
    row = next(line for line in out.splitlines() if "BibTeX tidy" in line and "Skipped" in line)
    assert "\u23ed" in row
    assert "\033[33mSkipped (bibtex-tidy not found)" in row
    assert "Build OK with warnings" in out


def test_multi_summary_names_skipped_checks(
    capsys: pytest.CaptureFixture[str], tmp_path: Path,
) -> None:
    skipped = CheckResult(name="BibTeX tidy", status=CheckStatus.SKIPPED)
    report.print_multi_summary(
        [("paper", BuildResult(output_dir=tmp_path, success=True), [skipped])],
    )
    out = capsys.readouterr().out
    assert "BibTeX tidy" in out
    assert "1 warn" in out
