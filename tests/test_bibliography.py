# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for project-wide bibliography checks (unused entries per bib file)."""

import os
import shutil
import time
from pathlib import Path

import pytest

from paperkit import bibliography as bib
from paperkit import report
from paperkit.builder import BuildResult
from paperkit.checks import CheckResult, CheckStatus
from paperkit.config import PaperkitConfig, load_config, parse_unused_bib

REFS = """\
@string{acm = "ACM"}
@article{A, title = {A}, journal = acm}
@article{B, title = {B}}
@article{C, title = {C}}
@comment{not an entry}
"""


# -- fixtures ------------------------------------------------------------------------


def _project(
    tmp_path: Path,
    mains: list[str],
    bibs: dict[str, str] | None = None,
) -> PaperkitConfig:
    for name, text in (bibs or {"refs.bib": REFS}).items():
        (tmp_path / name).write_text(text)
    for main in mains:
        (tmp_path / f"{main}.tex").write_text("\\documentclass{article}\n")
    cfg = PaperkitConfig(root=tmp_path, mains=list(mains), main=mains[0], bib="refs.bib")
    cfg.content_dirs = []
    return cfg


def _aux(cfg: PaperkitConfig, main: str, text: str, age: float = 0.0) -> BuildResult:
    """Write out/<main>/<main>.aux; *age* seconds in the future marks it fresh."""
    out = cfg.root / cfg.output_dir / main
    out.mkdir(parents=True, exist_ok=True)
    aux = out / f"{main}.aux"
    aux.write_text(text)
    if age:
        t = time.time() + age
        os.utime(aux, (t, t))
    return BuildResult(aux=aux, output_dir=out, success=True)


def _unused(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if r.name.startswith("Unused bib entries")]


def _keys(result: CheckResult) -> list[str]:
    return [m.strip() for m in result.messages[1:]]


# -- aux / bcf parsing --------------------------------------------------------------


def test_parse_aux_multiple_bibdata_and_citations(tmp_path: Path) -> None:
    aux = tmp_path / "p.aux"
    aux.write_text(
        "\\relax\n\\citation{A,B}\n\\citation{ C }\n\\bibstyle{plain}\n"
        "\\bibdata{refs, extra/more}\n",
    )
    data = bib.parse_aux(aux)
    assert data.bibdata == ["refs", "extra/more"]
    assert data.citations == {"A", "B", "C"}
    assert not data.cite_all


def test_parse_aux_follows_nested_input(tmp_path: Path) -> None:
    (tmp_path / "chapters").mkdir()
    (tmp_path / "p.aux").write_text("\\citation{A}\n\\@input{chapters/one.aux}\n\\bibdata{refs}\n")
    (tmp_path / "chapters" / "one.aux").write_text("\\citation{B}\n\\@input{two.aux}\n")
    # Nested \@input paths are relative to the main .aux's directory.
    (tmp_path / "two.aux").write_text("\\citation{C}\n\\@input{p.aux}\n")  # cycle
    data = bib.parse_aux(tmp_path / "p.aux")
    assert data.citations == {"A", "B", "C"}
    assert data.bibdata == ["refs"]


def test_parse_aux_nocite_star(tmp_path: Path) -> None:
    (tmp_path / "p.aux").write_text("\\citation{A}\n\\citation{*}\n")
    data = bib.parse_aux(tmp_path / "p.aux")
    assert data.cite_all
    assert data.citations == {"A"}


def test_parse_aux_biblatex_citations(tmp_path: Path) -> None:
    (tmp_path / "p.aux").write_text("\\abx@aux@cite{0}{A}\n\\abx@aux@cite{0}{B}\n")
    assert bib.parse_aux(tmp_path / "p.aux").citations == {"A", "B"}


def test_parse_bcf(tmp_path: Path) -> None:
    (tmp_path / "p.bcf").write_text(
        '<bcf:bibdata section="0">\n'
        '  <bcf:datasource type="file" datatype="bibtex" glob="false">refs.bib</bcf:datasource>\n'
        "</bcf:bibdata>\n"
        '<bcf:section number="0">\n'
        '  <bcf:citekey order="1" intorder="1">A</bcf:citekey>\n'
        '  <bcf:citekey order="2" intorder="1">*</bcf:citekey>\n'
        "</bcf:section>\n",
    )
    data = bib.parse_bcf(tmp_path / "p.bcf")
    assert data.bibdata == ["refs.bib"]
    assert data.citations == {"A"}
    assert data.cite_all


def test_bib_entry_keys_skip_strings_and_comments(tmp_path: Path) -> None:
    (tmp_path / "refs.bib").write_text(REFS)
    assert bib.bib_entry_keys(tmp_path / "refs.bib") == {"A", "B", "C"}


def test_resolve_bib_file_ignores_files_outside_project(tmp_path: Path) -> None:
    (tmp_path / "refs.bib").write_text(REFS)
    assert bib.resolve_bib_file(tmp_path, "refs") == (tmp_path / "refs.bib").resolve()
    assert bib.resolve_bib_file(tmp_path, "refs.bib") == (tmp_path / "refs.bib").resolve()
    assert bib.resolve_bib_file(tmp_path, "IEEEabrv") is None


# -- per-bib-file checks ------------------------------------------------------------


def test_shared_bib_reports_only_entries_no_target_cites(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper", "report"])
    outputs = {
        "paper": _aux(cfg, "paper", "\\citation{A}\n\\bibdata{refs}\n"),
        "report": _aux(cfg, "report", "\\citation{B}\n\\bibdata{refs}\n"),
    }
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=["paper", "report"]))
    assert result.status == CheckStatus.WARNING
    assert result.messages[0] == "1 unused bib entry/entries (cited by no target: paper, report):"
    assert _keys(result) == ["C"]


def test_nocite_star_in_any_user_uses_every_entry(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper", "report", "appendix"])
    outputs = {
        "paper": _aux(cfg, "paper", "\\citation{A}\n\\bibdata{refs}\n"),
        "report": _aux(cfg, "report", "\\citation{B}\n\\bibdata{refs}\n"),
        "appendix": _aux(cfg, "appendix", "\\citation{*}\n\\bibdata{refs}\n"),
    }
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=list(outputs)))
    assert result.status == CheckStatus.CLEAN
    assert result.messages[0].startswith("All bib entries are cited")


def test_different_bib_files_checked_against_their_own_users(tmp_path: Path) -> None:
    cfg = _project(
        tmp_path,
        ["paper", "report"],
        bibs={"refs.bib": REFS, "other.bib": "@misc{X, title={X}}\n@misc{Y, title={Y}}\n"},
    )
    outputs = {
        # paper cites B, but B lives in refs.bib, which only paper uses.
        "paper": _aux(cfg, "paper", "\\citation{A,B}\n\\bibdata{refs}\n"),
        "report": _aux(cfg, "report", "\\citation{X,C}\n\\bibdata{other}\n"),
    }
    results = _unused(bib.project_bib_checks(cfg, outputs, focus=["paper", "report"]))
    by_name = {r.name: r for r in results}
    assert set(by_name) == {"Unused bib entries (refs.bib)", "Unused bib entries (other.bib)"}
    # report cites C, but refs.bib is not one of report's bib files.
    assert _keys(by_name["Unused bib entries (refs.bib)"]) == ["C"]
    assert _keys(by_name["Unused bib entries (other.bib)"]) == ["Y"]


def test_ignore_list(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    cfg.checks.unused_bib.ignore = ["C"]
    outputs = {"paper": _aux(cfg, "paper", "\\citation{A}\n\\bibdata{refs}\n")}
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=["paper"]))
    assert _keys(result) == ["B"]


def test_single_main_keeps_legacy_wording(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    outputs = {"paper": _aux(cfg, "paper", "\\citation{A}\n\\bibdata{refs}\n")}
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=["paper"]))
    assert result.name == "Unused bib entries"
    assert result.messages == ["2 unused bib entry/entries:", "  B", "  C"]


def test_single_main_without_aux_is_skipped(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    cfg.checks.unused_bib.draft_pass = False  # keep the suite free of real engine runs
    outputs = {"paper": BuildResult(output_dir=tmp_path / "out" / "paper", success=True)}
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=["paper"]))
    assert result.status == CheckStatus.CLEAN
    assert result.messages == ["Skipped (aux or bib file not found)"]


def test_draft_pass_without_the_engine_installed(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    cfg.engine = "pdflatex-that-is-not-installed"
    assert bib.draft_usage(cfg, "paper") is None


def test_configured_bib_not_declared_is_checked_against_focus(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper"])
    outputs = {"paper": _aux(cfg, "paper", "\\citation{A}\n")}  # no \bibdata
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=["paper"]))
    assert _keys(result) == ["B", "C"]


# -- subset builds: other targets ----------------------------------------------------


def test_subset_reuses_fresh_aux_of_other_target(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper", "report"])
    _aux(cfg, "report", "\\citation{B}\n\\bibdata{refs}\n", age=60)
    outputs = {"paper": _aux(cfg, "paper", "\\citation{A}\n\\bibdata{refs}\n")}
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=["paper"]))
    assert result.status == CheckStatus.WARNING
    assert _keys(result) == ["C"]


def test_subset_stale_aux_uses_draft_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _project(tmp_path, ["paper", "report"])
    _aux(cfg, "report", "\\citation{A}\n\\bibdata{refs}\n", age=-60)  # stale
    calls = []

    def fake_draft(config: PaperkitConfig, name: str) -> bib.TargetUsage:
        calls.append(name)
        return bib.TargetUsage(name, {(tmp_path / "refs.bib").resolve()}, {"B"}, False, "draft")

    monkeypatch.setattr(bib, "draft_usage", fake_draft)
    outputs = {"paper": _aux(cfg, "paper", "\\citation{A}\n\\bibdata{refs}\n")}
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=["paper"]))
    assert calls == ["report"]
    assert _keys(result) == ["C"]


def test_subset_without_draft_pass_never_reports_unused(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["paper", "report"])
    cfg.checks.unused_bib.draft_pass = False
    _aux(cfg, "paper", "\\citation{A}\n\\bibdata{refs}\n", age=-60)  # stale
    outputs = {"report": _aux(cfg, "report", "\\citation{B}\n\\bibdata{refs}\n")}
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=["report"]))
    assert result.status == CheckStatus.CLEAN
    assert result.show_details
    assert result.messages[0] == "2 not cited by report; other targets not checked: paper"
    assert _keys(result) == ["A", "C"]


def test_failed_draft_pass_counts_as_not_checked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _project(tmp_path, ["paper", "report"])
    monkeypatch.setattr(bib, "draft_usage", lambda config, name: None)
    outputs = {"paper": _aux(cfg, "paper", "\\citation{A}\n\\bibdata{refs}\n")}
    [result] = _unused(bib.project_bib_checks(cfg, outputs, focus=["paper"]))
    assert result.status == CheckStatus.CLEAN
    assert "other targets not checked: report" in result.messages[0]


def test_failed_build_in_this_run_is_not_checked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _project(tmp_path, ["paper", "report"])
    monkeypatch.setattr(bib, "draft_usage", lambda config, name: pytest.fail("no draft pass"))
    outputs = {"paper": _aux(cfg, "paper", "\\citation{A}\n\\bibdata{refs}\n")}
    results = bib.project_bib_checks(cfg, outputs, focus=["paper", "report"], failed={"report"})
    assert "other targets not checked: report" in _unused(results)[0].messages[0]


def test_source_change_makes_aux_stale(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["report"])
    (tmp_path / "body").mkdir()
    cfg.content_dirs = ["body"]
    _aux(cfg, "report", "\\citation{B}\n\\bibdata{refs}\n", age=60)
    aux = tmp_path / "out" / "report" / "report.aux"
    usage = bib.usage_from_dir(cfg, "report", aux.parent, "existing .aux")
    assert usage is not None
    assert bib.is_up_to_date(cfg, usage, aux)
    section = tmp_path / "body" / "intro.tex"
    section.write_text("new text\n")
    t = time.time() + 120
    os.utime(section, (t, t))
    assert not bib.is_up_to_date(cfg, usage, aux)


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="needs pdflatex")
def test_draft_pass_reads_citations_without_touching_output(tmp_path: Path) -> None:
    cfg = _project(tmp_path, ["report"])
    (tmp_path / "report.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\cite{B}\\nocite{A}\n\\bibliographystyle{plain}\\bibliography{refs}\n"
        "\\end{document}\n",
    )
    cfg.shell_escape = False
    usage = bib.draft_usage(cfg, "report")
    assert usage is not None
    assert usage.citations == {"A", "B"}
    assert usage.bib_files == {(tmp_path / "refs.bib").resolve()}
    assert not (tmp_path / "out").exists()


# -- config ------------------------------------------------------------------------


def test_unused_bib_config_forms(tmp_path: Path) -> None:
    assert parse_unused_bib(False).enabled is False
    table = parse_unused_bib({"ignore": ["k"], "draft_pass": False})
    assert (table.enabled, table.ignore, table.draft_pass) == (True, ["k"], False)
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text('[project]\nmain = "p"\n\n[checks.unused_bib]\nignore = ["x"]\n')
    assert load_config(cfg_path).checks.unused_bib.ignore == ["x"]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("yes", "expected true, false or a table"),
        ({"draft": True}, "unknown key"),
        ({"ignore": "x"}, "list of strings"),
        ({"draft_pass": "no"}, "true or false"),
    ],
)
def test_unused_bib_config_errors(raw: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_unused_bib(raw)


# -- report ----------------------------------------------------------------------------


def test_multi_summary_prints_shared_bibliography_once(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    unused = CheckResult(
        name="Unused bib entries",
        status=CheckStatus.WARNING,
        messages=["1 unused bib entry/entries (cited by no target: paper, report):", "  C"],
    )
    runs = [
        ("paper", BuildResult(output_dir=tmp_path, success=True), [CheckResult(name="LaTeX")]),
        ("report", BuildResult(output_dir=tmp_path, success=True), [CheckResult(name="LaTeX")]),
    ]
    report.print_multi_summary(runs, [unused])
    out = capsys.readouterr().out
    assert out.count("cited by no target: paper, report") == 2  # details + summary row
    assert "Bibliography" in out
    assert "see warnings" in out
    assert "bibliography: warn" in out
