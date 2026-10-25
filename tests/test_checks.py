# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the per-target checks that read logs, sources and pdffonts output."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from paperkit import checks
from paperkit.checks import (
    CheckStatus,
    check_final_newline,
    check_font_embedding,
    check_log_errors,
    check_non_ascii,
    check_overfull_boxes,
    check_trailing_whitespace,
)
from paperkit.config import PaperkitConfig


def _project(tmp_path: Path, **files: str | bytes) -> PaperkitConfig:
    """A project with the given files; keys use / for subdirectories."""
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
    cfg = PaperkitConfig(root=tmp_path, main="paper", mains=["paper"])
    cfg.content_dirs = ["content"]
    return cfg


# -- logs ------------------------------------------------------------------------------


def test_missing_log_is_clean_and_silent(tmp_path: Path) -> None:
    result = check_log_errors(tmp_path / "paper.log", "LaTeX")
    assert result.status == CheckStatus.CLEAN
    assert result.messages == []


def test_clean_log(tmp_path: Path) -> None:
    log = tmp_path / "paper.log"
    log.write_text("This is pdfTeX\nOutput written on paper.pdf (3 pages).\n")
    result = check_log_errors(log, "LaTeX")
    assert (result.status, result.messages) == (CheckStatus.CLEAN, ["clean"])


def test_warnings_are_counted(tmp_path: Path) -> None:
    log = tmp_path / "paper.log"
    log.write_text("LaTeX Warning: Citation `x' undefined.\nPackage hyperref Warning: Token.\n")
    result = check_log_errors(log, "LaTeX")
    assert (result.status, result.messages) == (CheckStatus.WARNING, ["2 warning(s)"])


def test_known_false_positives_are_not_warnings(tmp_path: Path) -> None:
    log = tmp_path / "paper.log"
    log.write_text(
        "Package: infwarerr 2019/12/03 v1.5 Providing info/warning/error messages (HO)\n"
        "\\@latex@warning$ --\n"
        "> INFO - WARNINGS: 2\n",
    )
    result = check_log_errors(log, "LaTeX")
    assert result.status == CheckStatus.CLEAN, result.messages


def test_errors_are_grouped_with_their_line_numbers(tmp_path: Path) -> None:
    log = tmp_path / "paper.log"
    log.write_text(
        "! Undefined control sequence.\nl.12 \\foo\n\n"
        "! Undefined control sequence.\nl.40 \\bar\n\n"
        "! Missing $ inserted.\nl.7 x_1\n"
        "LaTeX Warning: something.\n",
    )
    result = check_log_errors(log, "LaTeX")
    assert result.status == CheckStatus.ERROR
    assert result.messages[0] == "3 error(s), 1 warning(s)"
    # Most frequent error first, with the range of lines it occurred on.
    undefined = ["2", "!", "Undefined", "control", "sequence.", "(l.12-40)"]
    assert result.messages[1].split() == undefined
    assert result.messages[2].split() == ["1", "!", "Missing", "$", "inserted.", "(l.7)"]


def test_biber_errors_and_warnings_use_their_own_markers(tmp_path: Path) -> None:
    blg = tmp_path / "paper.blg"
    blg.write_text("[1] > WARN - Duplicate entry key: x\n[2] > ERROR - Cannot find file\n")
    result = check_log_errors(blg, "Biber")
    assert result.status == CheckStatus.ERROR
    assert result.messages[0] == "1 error(s), 1 warning(s)"


# -- boxes -----------------------------------------------------------------------------


@pytest.mark.parametrize("log_path", [None, Path("/nonexistent/paper.log")])
def test_boxes_without_a_log_are_clean_and_silent(log_path: Path | None) -> None:
    result = check_overfull_boxes(log_path)
    assert (result.status, result.messages) == (CheckStatus.CLEAN, [])


def test_boxes_are_counted_and_overfull_ones_listed(tmp_path: Path) -> None:
    log = tmp_path / "paper.log"
    log.write_text(
        "Overfull \\hbox (12.3pt too wide) in paragraph at lines 5--6\n"
        "Underfull \\vbox (badness 10000) has occurred while \\output is active\n"
        "Underfull \\hbox (badness 1234) in paragraph at lines 9--10\n",
    )
    result = check_overfull_boxes(log)
    assert result.status == CheckStatus.WARNING
    assert result.messages[0] == "1 overfull, 2 underfull"
    assert result.messages[1].startswith("  Overfull \\hbox (12.3pt too wide)")
    assert len(result.messages) == 2  # underfull boxes are counted, not listed


def test_log_without_boxes_is_clean(tmp_path: Path) -> None:
    log = tmp_path / "paper.log"
    log.write_text("Output written on paper.pdf (1 page).\n")
    assert check_overfull_boxes(log).messages == ["clean"]


# -- source hygiene --------------------------------------------------------------------


def test_sources_are_the_content_dirs_and_the_mains(tmp_path: Path) -> None:
    cfg = _project(
        tmp_path,
        **{
            "paper.tex": "x\n",
            "content/a.tex": "x\n",
            "content/deep/b.tex": "x\n",
            "content/notes.txt": "ignored\n",
            "elsewhere/c.tex": "ignored\n",
        },
    )
    files = [str(f.relative_to(tmp_path)) for f in checks._collect_source_files(cfg)]
    assert files == ["content/a.tex", "content/deep/b.tex", "paper.tex"]


def test_missing_content_dir_and_main_are_tolerated(tmp_path: Path) -> None:
    cfg = _project(tmp_path)
    assert checks._collect_source_files(cfg) == []
    assert check_non_ascii(cfg).status == CheckStatus.CLEAN


def test_non_ascii_reports_file_line_and_text(tmp_path: Path) -> None:
    cfg = _project(tmp_path, **{"paper.tex": "ok\n", "content/a.tex": b"fine\ncaf\xc3\xa9\n"})
    result = check_non_ascii(cfg)
    assert result.status == CheckStatus.WARNING
    assert result.messages == ["content/a.tex:", "  2: caf\u00e9"]


def test_ascii_sources_are_clean(tmp_path: Path) -> None:
    cfg = _project(tmp_path, **{"paper.tex": "ok\n"})
    result = check_non_ascii(cfg)
    assert (result.status, result.messages) == (
        CheckStatus.CLEAN,
        ["All source .tex files are ASCII-clean"],
    )


def test_trailing_whitespace_counts_lines_per_file(tmp_path: Path) -> None:
    cfg = _project(tmp_path, **{"paper.tex": "a \nb\nc  \n", "content/a.tex": "clean\n"})
    result = check_trailing_whitespace(cfg)
    assert result.status == CheckStatus.WARNING
    assert result.messages == ["2 line(s) with trailing whitespace:", "  paper.tex (2 lines)"]


def test_no_trailing_whitespace_is_clean(tmp_path: Path) -> None:
    cfg = _project(tmp_path, **{"paper.tex": "a\nb\n"})
    assert check_trailing_whitespace(cfg).messages == ["No trailing whitespace found"]


def test_final_newline_distinguishes_the_three_defects(tmp_path: Path) -> None:
    cfg = _project(
        tmp_path,
        **{
            "paper.tex": "good\n",
            "content/empty.tex": "",
            "content/none.tex": "no newline",
            "content/two.tex": "two\n\n",
        },
    )
    result = check_final_newline(cfg)
    assert result.status == CheckStatus.WARNING
    assert result.messages == [
        "content/empty.tex: empty file",
        "content/none.tex: no final newline",
        "content/two.tex: multiple trailing newlines",
    ]


def test_single_final_newline_is_clean(tmp_path: Path) -> None:
    cfg = _project(tmp_path, **{"paper.tex": "good\n"})
    assert check_final_newline(cfg).status == CheckStatus.CLEAN


# -- fonts -----------------------------------------------------------------------------

# pdffonts output as poppler prints it: columns sized by the dashed separator.
_WIDTHS = (36, 17, 16, 3, 3, 3, 9)


def _row(*fields: str) -> str:
    return " ".join(f"{f:<{w}}" for f, w in zip(fields, _WIDTHS, strict=True)).rstrip()


HEADER = _row("name", "type", "encoding", "emb", "sub", "uni", "object ID")
SEPARATOR = " ".join("-" * w for w in _WIDTHS)
ROMAN = _row("ABCDEF+NimbusRomNo9L-Regu", "Type 1", "Custom", "yes", "yes", "no", "7 0")
TYPE3 = _row("GHIJKL+CMR10", "Type 3", "Custom", "yes", "no", "no", "12 0")
HELVETICA = _row("Helvetica", "Type 1", "WinAnsi", "no", "no", "no", "15 0")
LONG_NAME = _row(
    "MNOPQR+ALongFontNameThatOverflowsItsColumn", "Type 1C", "Custom", "yes", "yes", "no", "20 0"
)


def _fake_pdffonts(
    monkeypatch: pytest.MonkeyPatch,
    whole: list[str],
    per_page: dict[int, list[str]] | None = None,
) -> list[list[str]]:
    """Answer pdffonts calls from canned rows; return the commands seen."""
    calls: list[list[str]] = []

    def run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(cmd)
        rows = whole
        if "-f" in cmd:
            rows = (per_page or {}).get(int(cmd[cmd.index("-f") + 1]), [])
        return SimpleNamespace(stdout="\n".join([HEADER, SEPARATOR, *rows]) + "\n", returncode=0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(checks.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(checks.pages, "get_total_pages", lambda pdf: len(per_page or {}))
    return calls


def _pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.5\n")
    return pdf


def test_columns_come_from_the_separator() -> None:
    columns = checks._pdffonts_columns(HEADER, SEPARATOR)
    assert list(columns) == ["name", "type", "encoding", "emb", "sub", "uni", "object id"]
    assert columns["name"] == (0, 36)
    assert columns["emb"] == (36 + 17 + 16 + 3, 36 + 17 + 16 + 3 + 3)


def test_all_embedded_no_type3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = _pdf(tmp_path)
    _fake_pdffonts(monkeypatch, [ROMAN, LONG_NAME])
    result = check_font_embedding(pdf)
    assert result.status == CheckStatus.CLEAN
    assert result.messages[0] == "2/2 embedded, no Type 3"
    report = pdf.with_name("fonts.txt")
    assert report.is_file()
    assert "# pdffonts" in report.read_text()
    assert result.messages[-1] == f"Full font report: {report}"


def test_unembedded_font_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pdffonts(monkeypatch, [ROMAN, HELVETICA])
    result = check_font_embedding(_pdf(tmp_path))
    assert result.status == CheckStatus.ERROR
    assert result.messages[0] == "1/2 NOT embedded, no Type 3"
    assert result.messages[1] == "Not embedded:"
    assert result.messages[2].strip().startswith("Helvetica")


def test_type3_is_a_warning_located_per_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf(tmp_path)
    pages_with = {1: [ROMAN], 2: [TYPE3], 3: [TYPE3]}
    calls = _fake_pdffonts(monkeypatch, [ROMAN, TYPE3], per_page=pages_with)
    result = check_font_embedding(pdf)
    assert result.status == CheckStatus.WARNING
    assert result.messages[0] == "2/2 embedded, 1 Type 3 (bitmap)"
    assert result.messages[1] == "Type 3 (bitmap):"
    assert result.messages[2].endswith("(p. 2, 3)")
    assert any("matplotlib" in m and "cm-super" in m for m in result.messages)
    # One pdffonts call for the whole PDF, then one per page.
    assert [c[1:3] for c in calls[1:]] == [["-f", "1"], ["-f", "2"], ["-f", "3"]]
    assert "# Type 3 (bitmap) fonts" in pdf.with_name("fonts.txt").read_text()


def test_type3_can_be_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pdffonts(monkeypatch, [ROMAN, TYPE3])
    result = check_font_embedding(_pdf(tmp_path), no_type3=False)
    assert (result.status, result.messages[0]) == (CheckStatus.CLEAN, "2/2 embedded")


def test_unembedded_wins_over_type3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pdffonts(monkeypatch, [TYPE3, HELVETICA], per_page={1: [TYPE3]})
    result = check_font_embedding(_pdf(tmp_path))
    assert result.status == CheckStatus.ERROR
    assert result.messages[0] == "1/2 NOT embedded, 1 Type 3 (bitmap)"


def test_long_font_name_shifts_the_row_but_still_parses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The long name pushes every later column right; the parser compensates.
    _fake_pdffonts(monkeypatch, [LONG_NAME])
    result = check_font_embedding(_pdf(tmp_path))
    assert (result.status, result.messages[0]) == (CheckStatus.CLEAN, "1/1 embedded, no Type 3")


def test_pdf_without_fonts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pdffonts(monkeypatch, [])
    result = check_font_embedding(_pdf(tmp_path))
    assert (result.status, result.messages) == (CheckStatus.CLEAN, ["No fonts found"])


def test_missing_pdf_is_skipped(tmp_path: Path) -> None:
    result = check_font_embedding(tmp_path / "paper.pdf")
    assert result.status == CheckStatus.SKIPPED
    assert result.messages == ["Skipped (PDF not found)"]
