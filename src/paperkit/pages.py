# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Page-count analysis from PDF + aux file.

Extracts:
  * total pages       - via pdfinfo
  * refs start page   - from .aux TOC entries ("References"/"Bibliography"),
                        falling back to a pdftotext heading scan
  * ack  start page   - same, matching "Acknowledg..."
  * before refs/ack   - pages occupied by the content preceding each section
                        (a section starting mid-page counts that page)

Patterns are configurable for non-English papers. Page limits in
[page_limits] flip the check to ERROR when exceeded.

Page numbers are the same in single- and double-column layouts (a page is a
page), so this module needs no layout awareness.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PageStats:
    total: int | None = None
    refs_page: int | None = None
    ack_page: int | None = None
    # Number of pages occupied by the content preceding each section. By
    # default refs and ack form one exempt tail, so both hold the pages before
    # whichever comes first: content of one exempt section must not count
    # against the other's limit. With ack_counts_as_content the tail is the
    # references alone, and before_ack becomes the pages before the
    # acknowledgments. The page is counted when the section starts mid-page.
    before_refs: int | None = None
    before_ack: int | None = None


# Matches \@writefile{toc}{\contentsline {section}{TITLE}{PAGE}{ANCHOR}...}
# where TITLE may contain balanced nested braces. We pull TITLE with a manual
# brace scanner since regex can't track arbitrary nesting.
_TOC_PREFIX = r"\@writefile{toc}{\contentsline {section}{"


def _parse_toc_line(line: str) -> tuple[str, int] | None:
    """Return (raw_title, page) from one \\@writefile{toc} section line."""
    line = line.lstrip()
    if not line.startswith(_TOC_PREFIX):
        return None
    rest = line[len(_TOC_PREFIX) :]

    # Scan balanced braces for the title.
    depth = 1
    i = 0
    while i < len(rest) and depth > 0:
        c = rest[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    if depth != 0 or i >= len(rest):
        return None
    title = rest[:i]
    rest = rest[i + 1 :]

    # Expect {PAGE}
    if not rest.startswith("{"):
        return None
    page_end = rest.find("}", 1)
    if page_end < 0:
        return None
    page_str = rest[1:page_end].strip()
    try:
        return title, int(page_str)
    except ValueError:
        return None  # roman numerals or odd page anchors: skip


def _clean_title(title: str) -> str:
    """Strip \\numberline{...}, \\mbox{...}, and other LaTeX command wrappers."""
    # \numberline {X} or \numberline{X}
    title = re.sub(r"\\numberline\s*\{[^{}]*\}", "", title)
    # Drop \mbox{...} wrappers around section numbers
    title = re.sub(r"\\mbox\s*\{([^{}]*)\}", r"\1", title)
    # Drop single-arg \cmd{content} wrappers, keep content
    for _ in range(3):
        title = re.sub(r"\\[a-zA-Z]+\s*\{([^{}]*)\}", r"\1", title)
    # Remove remaining lone commands
    title = re.sub(r"\\[a-zA-Z@]+", "", title)
    return title.replace("{", "").replace("}", "").strip()


def parse_toc(aux_path: Path) -> list[tuple[str, int]]:
    """Read .aux and return [(cleaned_title, page)] in document order."""
    if not aux_path.is_file():
        return []
    out: list[tuple[str, int]] = []
    for line in aux_path.read_text(errors="replace").splitlines():
        parsed = _parse_toc_line(line)
        if parsed is None:
            continue
        title, page = parsed
        out.append((_clean_title(title), page))
    return out


def find_section_page(toc: list[tuple[str, int]], pattern: str) -> int | None:
    """First TOC entry whose title matches *pattern* (used with re.search)."""
    rx = re.compile(pattern)
    for title, page in toc:
        if rx.search(title):
            return page
    return None


def _pdf_text_pages(pdf_path: Path) -> list[str] | None:
    """Extract per-page text via pdftotext (pages are form-feed separated)."""
    if not pdf_path.is_file() or shutil.which("pdftotext") is None:
        return None
    proc = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.split("\f")


def _is_heading_line(line: str, rx: re.Pattern[str]) -> bool:
    """True if *line* looks like a standalone section heading matching *rx*.

    Headings render as short lines; small-caps fonts may introduce spurious
    spaces ("R EFERENCES"), so we also match with spaces stripped.
    """
    line = line.strip()
    if not 0 < len(line) < 30:
        return False
    return bool(rx.search(line) or rx.search(line.replace(" ", "")))


def find_heading_pos(pages_text: list[str], pattern: str) -> tuple[int, int] | None:
    """Locate *pattern* as a standalone heading line in the rendered PDF text.

    Returns (page_num, line_index) of the first match, or None. Also serves
    as fallback detection for sections that don't write to \\@writefile{toc},
    such as IEEEtran's `\\section*{Acknowledgment}`.
    """
    rx = re.compile(pattern)
    for page_num, page_text in enumerate(pages_text, start=1):
        for line_idx, raw_line in enumerate(page_text.splitlines()):
            if _is_heading_line(raw_line, rx):
                return page_num, line_idx
    return None


def body_end_page(pages_text: list[str], heading_pos: tuple[int, int]) -> int:
    """Page on which the body content preceding *heading_pos* ends.

    If the heading sits at the top of its page (nothing but a running header
    or page number above it), the body ended on the previous page; otherwise
    it shares the heading's page. In double-column layouts pdftotext emits
    text in reading order, so a heading at the top of the second column is
    correctly preceded by first-column body text.
    """
    page, line_idx = heading_pos
    lines = pages_text[page - 1].splitlines()[:line_idx]
    preceding = sum(1 for raw_line in lines if raw_line.strip())
    # Tolerate a few short lines above the heading (running header, page number).
    return page if preceding > 2 else page - 1


def get_total_pages(pdf_path: Path) -> int | None:
    """Return total PDF pages via pdfinfo, or None if it can't be read."""
    if not pdf_path.is_file() or shutil.which("pdfinfo") is None:
        return None
    proc = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def content_end_pages(
    pages_text: list[str],
    refs_pos: tuple[int, int] | None,
    ack_pos: tuple[int, int] | None,
    ack_counts_as_content: bool = False,
) -> tuple[int | None, int | None]:
    """Pages occupied by the content before the references and before the acks.

    By default the two sections form one exempt tail: both values are the
    pages before whichever heading comes first, so acknowledgments sitting
    between the body and the references do not count against either limit.

    With *ack_counts_as_content* only the references are exempt, as at venues
    that count acknowledgments as text: the page budget then ends at the
    references heading, and the acknowledgments fall inside it.
    """
    if ack_counts_as_content:
        before_refs = body_end_page(pages_text, refs_pos) if refs_pos else None
        before_ack = body_end_page(pages_text, ack_pos) if ack_pos else None
        return before_refs, before_ack

    positions = [pos for pos in (refs_pos, ack_pos) if pos is not None]
    if not positions:
        return None, None
    end = body_end_page(pages_text, min(positions))
    return (end if refs_pos else None), (end if ack_pos else None)


def gather(
    pdf_path: Path | None,
    aux_path: Path | None,
    refs_pattern: str,
    ack_pattern: str,
    ack_counts_as_content: bool = False,
) -> PageStats:
    """Collect all page stats; missing inputs leave fields as None."""
    stats = PageStats()
    pages_text: list[str] | None = None
    if pdf_path is not None:
        stats.total = get_total_pages(pdf_path)
        pages_text = _pdf_text_pages(pdf_path)
    if aux_path is not None:
        toc = parse_toc(aux_path)
        stats.refs_page = find_section_page(toc, refs_pattern)
        stats.ack_page = find_section_page(toc, ack_pattern)
    if pages_text:
        refs_pos = find_heading_pos(pages_text, refs_pattern)
        ack_pos = find_heading_pos(pages_text, ack_pattern)
        # Fallback for sections missing from the TOC (e.g. IEEEtran's
        # `\section*{Acknowledgment}` doesn't emit `\@writefile{toc}`).
        if stats.refs_page is None and refs_pos is not None:
            stats.refs_page = refs_pos[0]
        if stats.ack_page is None and ack_pos is not None:
            stats.ack_page = ack_pos[0]
        stats.before_refs, stats.before_ack = content_end_pages(
            pages_text,
            refs_pos,
            ack_pos,
            ack_counts_as_content,
        )
    return stats
