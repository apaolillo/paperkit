# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for the plain-text title and abstract export."""

import shutil
from pathlib import Path

import pytest

from paperkit import text_export
from paperkit.config import PaperkitConfig

needs_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="needs pandoc")

MAIN = r"""\documentclass{article}
\input{header/commands}
% \input{header/commented_out}
\title{\sys{}: Structure-Preserving Translation}
\begin{document}
\maketitle
\input{body/abstract}
\input{body/intro}
\end{document}
"""
COMMANDS = r"""\newcommand{\sys}{Widget}
\makeatletter
\newcommand{\internal@thing}{hidden}
\makeatother
% A definition spanning several lines, as class files and rights blocks use.
\providecommand\BibTeX{{
  \rm B\kern-.05em\textsc{i\kern-.025em b}\kern-.08em T\kern-.1667em\kern-.125emX}}
"""
ABSTRACT = r"""\begin{abstract}
We present \sys{}, a translator. It keeps \emph{structure} intact.
\end{abstract}
"""


def _project(tmp_path: Path, main_body: str = MAIN) -> PaperkitConfig:
    (tmp_path / "header").mkdir()
    (tmp_path / "body").mkdir()
    (tmp_path / "paper.tex").write_text(main_body)
    (tmp_path / "header" / "commands.tex").write_text(COMMANDS)
    (tmp_path / "body" / "abstract.tex").write_text(ABSTRACT)
    # Nested include: resolved against the main file's directory, not body/.
    (tmp_path / "body" / "intro.tex").write_text("\\input{body/details}\n")
    (tmp_path / "body" / "details.tex").write_text("Details here.\n")
    (tmp_path / "header" / "commented_out.tex").write_text("\\title{WRONG}\n")
    return PaperkitConfig(root=tmp_path, main="paper", mains=["paper"])


# -- flatten ------------------------------------------------------------------------


def test_flatten_inlines_inputs_and_skips_comments(tmp_path: Path) -> None:
    cfg = _project(tmp_path)
    flat = text_export.flatten(cfg.root / "paper.tex")
    assert "\\newcommand{\\sys}{Widget}" in flat
    assert "We present \\sys{}, a translator." in flat
    assert "Details here." in flat  # nested, path relative to the main file
    assert "WRONG" not in flat  # the commented-out \input is not followed


def test_flatten_handles_missing_files_and_cycles(tmp_path: Path) -> None:
    (tmp_path / "a.tex").write_text("A\n\\input{b}\n\\input{nope}\n")
    (tmp_path / "b.tex").write_text("B\n\\input{a}\n")
    flat = text_export.flatten(tmp_path / "a.tex")
    assert "A" in flat
    assert flat.count("B") == 1  # the cycle back into a.tex stops there


def test_flatten_accepts_an_explicit_suffix_and_bare_argument(tmp_path: Path) -> None:
    (tmp_path / "m.tex").write_text("\\input{part.tex}\n\\input bare\n")
    (tmp_path / "part.tex").write_text("PART\n")
    (tmp_path / "bare.tex").write_text("BARE\n")
    flat = text_export.flatten(tmp_path / "m.tex")
    assert "PART" in flat
    assert "BARE" in flat


# -- exports ------------------------------------------------------------------------


@needs_pandoc
def test_writes_both_files_with_macros_expanded(tmp_path: Path) -> None:
    cfg = _project(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    result = text_export.write_text_exports(cfg, "paper", out)
    assert [p.name for p in result.written] == ["title.txt", "abstract.txt"]
    assert result.warnings == []
    title = (out / "title.txt").read_text()
    abstract = (out / "abstract.txt").read_text()
    assert title.strip() == "Widget: Structure-Preserving Translation"
    assert abstract.startswith("We present Widget, a translator.")
    for text in (title, abstract):
        assert "\\" not in text  # no LaTeX left
        assert "{" not in text


@needs_pandoc
def test_missing_title_and_abstract_are_reported(tmp_path: Path) -> None:
    cfg = _project(
        tmp_path, main_body="\\documentclass{article}\n\\begin{document}\nx\n\\end{document}\n"
    )
    out = tmp_path / "out"
    out.mkdir()
    result = text_export.write_text_exports(cfg, "paper", out)
    assert result.written == []
    assert result.warnings == [
        "title.txt skipped: no \\title found",
        "abstract.txt skipped: no abstract found",
    ]


@needs_pandoc
def test_multiline_macro_definitions_do_not_break_the_export(tmp_path: Path) -> None:
    # Half of a multi-line definition would unbalance the snippet and pandoc
    # would refuse the whole input, losing both files.
    cfg = _project(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    result = text_export.write_text_exports(cfg, "paper", out)
    assert result.warnings == []
    assert (out / "title.txt").read_text().strip() == "Widget: Structure-Preserving Translation"


def test_extract_macros_keeps_only_balanced_definitions() -> None:
    macros = text_export._extract_macros(COMMANDS)
    assert "\\newcommand{\\sys}{Widget}" in macros
    assert "BibTeX" not in macros  # spans two lines
    assert "internal@thing" not in macros  # internal


def test_missing_pandoc_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _project(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(text_export.shutil, "which", lambda _name: None)
    result = text_export.write_text_exports(cfg, "paper", out)
    assert result.written == []
    assert result.warnings == ["title.txt/abstract.txt skipped: pandoc not found"]
    assert not list(out.iterdir())


def test_missing_main_file_is_reported(tmp_path: Path) -> None:
    cfg = PaperkitConfig(root=tmp_path, main="ghost", mains=["ghost"])
    result = text_export.write_text_exports(cfg, "ghost", tmp_path)
    assert result.warnings == ["title.txt/abstract.txt skipped: ghost.tex not found"]


def test_print_shows_written_files_and_warnings(capsys: pytest.CaptureFixture[str]) -> None:
    result = text_export.TextExportResult(
        written=[Path("out/paper/title.txt")],
        warnings=["abstract.txt skipped: no abstract found"],
    )
    text_export.print_text_exports(result)
    out = capsys.readouterr().out
    assert "title.txt" in out
    assert "abstract.txt skipped: no abstract found" in out


def test_print_is_quiet_when_there_is_nothing_to_say(
    capsys: pytest.CaptureFixture[str],
) -> None:
    text_export.print_text_exports(text_export.TextExportResult())
    assert capsys.readouterr().out == ""
