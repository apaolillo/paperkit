# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for finding, loading and validating .paperkit.toml."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from paperkit import cli
from paperkit.config import find_config, load_config


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".paperkit.toml"
    path.write_text(text)
    return path


# -- finding ---------------------------------------------------------------------------


def test_find_config_walks_up(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    nested = tmp_path / "content" / "deep"
    nested.mkdir(parents=True)
    assert find_config(nested) == path


def test_find_config_without_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The search stops at the filesystem root; make sure nothing above
    # tmp_path can be found by pretending tmp_path has no parent config.
    with pytest.raises(FileNotFoundError, match="No .paperkit.toml"):
        find_config(Path("/"))


def test_root_is_the_config_directory(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    assert load_config(path).root == tmp_path.resolve()


# -- defaults and [project] ------------------------------------------------------------


def test_empty_file_gives_the_documented_defaults(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, ""))
    assert (cfg.main, cfg.mains) == ("main", ["main"])
    assert cfg.content_dirs == ["content"]
    assert cfg.bib == ""
    assert (cfg.engine, cfg.passes, cfg.shell_escape) == ("pdflatex", 3, True)
    assert (cfg.bibtex, cfg.biber, cfg.output_dir, cfg.jobs) == (True, False, "out", None)
    assert cfg.source_date_epoch == "git"
    assert (cfg.base_image, cfg.image_name) == ("ubuntu:26.04", "paperkit-builder")
    assert cfg.texlive.source == "distro"
    assert cfg.page_limits.total is None
    assert cfg.zip.name == "main"
    assert cfg.zip.exclude == ["*.aux", "*.log", "*.out", "*.blg", "*.bbl"]
    assert cfg.profile_name == "acm"


def test_main_and_mains_are_merged_in_order_without_duplicates(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, '[project]\nmain = "a"\nmains = ["b", "a", "c"]\n'))
    assert (cfg.main, cfg.mains) == ("a", ["a", "b", "c"])


def test_main_may_be_a_list(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, '[project]\nmain = ["x", "y"]\n'))
    assert cfg.mains == ["x", "y"]


def test_main_glob_expands_sorted_against_the_root(tmp_path: Path) -> None:
    for name in ("paper-b", "paper-a", "notes"):
        (tmp_path / f"{name}.tex").write_text("")
    cfg = load_config(_write(tmp_path, '[project]\nmain = "paper-*"\n'))
    assert cfg.mains == ["paper-a", "paper-b"]


def test_main_glob_matching_nothing_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="matched no .tex files"):
        load_config(_write(tmp_path, '[project]\nmain = "paper-*"\n'))


def test_main_of_the_wrong_type_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\[project\] main"):
        load_config(_write(tmp_path, "[project]\nmain = 3\n"))


# -- the other tables ------------------------------------------------------------------


def test_build_and_docker_keys_are_read(tmp_path: Path) -> None:
    cfg = load_config(
        _write(
            tmp_path,
            '[build]\nengine = "xelatex"\npasses = 4\nshell_escape = false\n'
            'bibtex = false\nbiber = true\noutput_dir = "build"\njobs = 2\n'
            "source_date_epoch = 1700000000\n"
            '[docker]\nbase_image = "ubuntu:24.04"\nimage_name = "x"\n'
            'extra_packages = ["cm-super"]\ndebconf_selections = ["a b c d"]\n',
        ),
    )
    assert (cfg.engine, cfg.passes, cfg.shell_escape) == ("xelatex", 4, False)
    assert (cfg.bibtex, cfg.biber, cfg.output_dir, cfg.jobs) == (False, True, "build", 2)
    assert cfg.source_date_epoch == 1700000000
    assert (cfg.base_image, cfg.image_name) == ("ubuntu:24.04", "x")
    assert (cfg.extra_packages, cfg.debconf_selections) == (["cm-super"], ["a b c d"])


def test_check_switches_and_nested_tables(tmp_path: Path) -> None:
    cfg = load_config(
        _write(
            tmp_path,
            "[checks]\nnon_ascii = false\nno_type3 = false\nunused_bib = false\n"
            'bibtex_tidy = { enabled = false, version = "1.13.0", sort = false }\n',
        ),
    )
    assert (cfg.checks.non_ascii, cfg.checks.no_type3) == (False, False)
    assert cfg.checks.trailing_whitespace is True  # untouched
    assert cfg.checks.unused_bib.enabled is False
    bt = cfg.checks.bibtex_tidy
    assert (bt.enabled, bt.version, bt.sort) == (False, "1.13.0", False)


def test_bibtex_tidy_sort_must_be_a_bool(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bibtex_tidy.sort"):
        load_config(_write(tmp_path, '[checks]\nbibtex_tidy = { sort = "yes" }\n'))


def test_page_limits_are_read_and_validated(tmp_path: Path) -> None:
    cfg = load_config(
        _write(
            tmp_path,
            "[page_limits]\ntotal = 14\nbefore_refs = 12\nbefore_ack = 11\n"
            'ack_counts_as_content = true\nrefs_pattern = "(?i)literatur"\n',
        ),
    )
    pl = cfg.page_limits
    assert (pl.total, pl.before_refs, pl.before_ack) == (14, 12, 11)
    assert pl.ack_counts_as_content is True
    assert pl.refs_pattern == "(?i)literatur"
    with pytest.raises(ValueError, match="ack_counts_as_content"):
        load_config(_write(tmp_path, "[page_limits]\nack_counts_as_content = 1\n"))


def test_zip_name_defaults_to_the_first_main(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, '[project]\nmain = "thesis"\n[zip]\ninclude = ["*.tex"]\n'))
    assert (cfg.zip.name, cfg.zip.include) == ("thesis", ["*.tex"])
    cfg = load_config(_write(tmp_path, '[zip]\nname = "submission"\ninclude_bbl = true\n'))
    assert (cfg.zip.name, cfg.zip.include_bbl) == ("submission", True)
    with pytest.raises(ValueError, match="include_bbl"):
        load_config(_write(tmp_path, '[zip]\ninclude_bbl = "yes"\n'))


def test_profile_name_is_read(tmp_path: Path) -> None:
    assert load_config(_write(tmp_path, '[profile]\nname = "base"\n')).profile_name == "base"


# -- how the CLI reports a bad config --------------------------------------------------


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ('[texlive]\nsource = "upstream"\nsnapshot = "not-a-date"\n', "snapshot"),
        ('[profile]\nname = "amc"\n', "unknown profile 'amc'"),
        ('[project]\nmain = "missing-*"\n', "matched no .tex files"),
    ],
)
def test_a_bad_config_is_an_error_message_not_a_traceback(
    tmp_path: Path,
    text: str,
    fragment: str,
) -> None:
    path = _write(tmp_path, text)
    result = CliRunner().invoke(cli.main, ["--config", str(path), "zip"])
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.output
    assert result.output.startswith("error: ")
    assert fragment in result.output
