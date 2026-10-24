# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for page-limit arithmetic, including acknowledgments as content."""

from pathlib import Path

import pytest

from paperkit import checks, pages
from paperkit.builder import BuildResult
from paperkit.checks import CheckStatus
from paperkit.config import PaperkitConfig, load_config

BODY = "body text\n" * 30


def _page(*headings: str) -> str:
    """A page whose headings sit after a running header and body text."""
    out = ["running header"]
    for heading in headings:
        out.append(BODY)
        out.append(heading)
    out.append(BODY)
    return "\n".join(out)


def _top(heading: str) -> str:
    """A page starting with *heading* (only a running header above it)."""
    return f"running header\n{heading}\n{BODY}"


def _ends(pages_text: list[str], ack_counts: bool = False) -> tuple[int | None, int | None]:
    refs = pages.find_heading_pos(pages_text, r"(?i)\b(references|bibliography)\b")
    ack = pages.find_heading_pos(pages_text, r"(?i)acknowledg")
    return pages.content_end_pages(pages_text, refs, ack, ack_counts)


# -- fixtures from the acceptance list ---------------------------------------------


def _acks_after_limit() -> list[str]:
    """14 pages of body; p15 starts with the acks, references follow on p15."""
    return [_page() for _ in range(14)] + [_top("Acknowledgments") + "\nReferences\n"]


def _acks_inside_limit() -> list[str]:
    """Body runs to p13; p14 starts with the acks and has the references below."""
    return [_page() for _ in range(13)] + [_top("Acknowledgments") + BODY + "\nReferences\n"]


def _no_acks() -> list[str]:
    """14 pages of body, references at the top of p15."""
    return [_page() for _ in range(14)] + [_top("References")]


def _refs_before_acks() -> list[str]:
    """References at the top of p15, acknowledgments after them."""
    return [_page() for _ in range(14)] + [_top("References") + BODY + "\nAcknowledgments\n"]


def test_acks_after_limit_are_exempt_by_default() -> None:
    # Both sections are the exempt tail: the body ends before the acks.
    assert _ends(_acks_after_limit()) == (14, 14)


def test_acks_after_limit_count_as_content_with_the_flag() -> None:
    # Only the references are exempt, so the acks push the body to p15.
    assert _ends(_acks_after_limit(), ack_counts=True) == (15, 14)


def test_acks_inside_limit_pass_in_both_modes() -> None:
    assert _ends(_acks_inside_limit()) == (13, 13)
    assert _ends(_acks_inside_limit(), ack_counts=True) == (14, 13)


def test_without_acknowledgments_both_modes_agree() -> None:
    assert _ends(_no_acks()) == (14, None)
    assert _ends(_no_acks(), ack_counts=True) == (14, None)


def test_references_before_acknowledgments() -> None:
    # The body ends at the references either way; only before_ack differs.
    assert _ends(_refs_before_acks()) == (14, 14)
    assert _ends(_refs_before_acks(), ack_counts=True) == (14, 15)


def test_no_sections_at_all() -> None:
    assert _ends([_page() for _ in range(3)]) == (None, None)
    assert _ends([_page() for _ in range(3)], ack_counts=True) == (None, None)


# -- config ------------------------------------------------------------------------


def test_flag_defaults_to_false() -> None:
    assert PaperkitConfig().page_limits.ack_counts_as_content is False


def test_config_reads_the_flag(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text(
        '[project]\nmain = "p"\n\n[page_limits]\nbefore_refs = 14\nack_counts_as_content = true\n',
    )
    limits = load_config(cfg_path).page_limits
    assert limits.ack_counts_as_content is True
    assert limits.before_refs == 14


def test_config_rejects_non_boolean_flag(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".paperkit.toml"
    cfg_path.write_text(
        '[project]\nmain = "p"\n\n[page_limits]\nack_counts_as_content = "yes"\n',
    )
    with pytest.raises(ValueError, match="true or false"):
        load_config(cfg_path)


# -- report line -------------------------------------------------------------------


def _check(
    monkeypatch: pytest.MonkeyPatch, stats: pages.PageStats, **limits: object
) -> tuple[CheckStatus, str]:
    cfg = PaperkitConfig()
    for key, value in limits.items():
        setattr(cfg.page_limits, key, value)
    monkeypatch.setattr(pages, "gather", lambda **kwargs: stats)
    result = checks.check_pages(cfg, BuildResult(pdf=Path("paper.pdf")))
    return result.status, result.messages[0]


def test_report_flags_the_overage_and_says_acks_are_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stats = pages.PageStats(total=16, refs_page=15, ack_page=15, before_refs=15, before_ack=14)
    status, summary = _check(monkeypatch, stats, before_refs=14, ack_counts_as_content=True)
    assert status == CheckStatus.ERROR
    assert "before refs 15/14 (refs start p.15; acks counted)" in summary
    assert "\u274c" in summary


def test_report_unchanged_without_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    stats = pages.PageStats(total=16, refs_page=15, ack_page=15, before_refs=14, before_ack=14)
    status, summary = _check(monkeypatch, stats, before_refs=14)
    assert status == CheckStatus.CLEAN
    assert "before refs 14/14 (refs start p.15) \u2714" in summary
    assert "acks counted" not in summary
