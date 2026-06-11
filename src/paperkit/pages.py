"""Page-count analysis from PDF + aux file.

Extracts:
  * total pages       — via pdfinfo
  * refs start page   — by scanning .aux TOC entries for "References" or
                        "Bibliography"
  * ack  start page   — by scanning .aux TOC entries for "Acknowledg..."

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


# Matches \@writefile{toc}{\contentsline {section}{TITLE}{PAGE}{ANCHOR}...}
# where TITLE may contain balanced nested braces. We pull TITLE with a manual
# brace scanner since regex can't track arbitrary nesting.
_TOC_PREFIX = r"\@writefile{toc}{\contentsline {section}{"


def _parse_toc_line(line: str) -> tuple[str, int] | None:
    """Return (raw_title, page) from one \\@writefile{toc} section line."""
    line = line.lstrip()
    if not line.startswith(_TOC_PREFIX):
        return None
    rest = line[len(_TOC_PREFIX):]

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
    rest = rest[i + 1:]

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
        return None  # roman numerals or odd page anchors — skip


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
    title = title.replace("{", "").replace("}", "").strip()
    return title


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


def gather(
    pdf_path: Path | None,
    aux_path: Path | None,
    refs_pattern: str,
    ack_pattern: str,
) -> PageStats:
    """Collect all page stats; missing inputs leave fields as None."""
    stats = PageStats()
    if pdf_path is not None:
        stats.total = get_total_pages(pdf_path)
    if aux_path is not None:
        toc = parse_toc(aux_path)
        stats.refs_page = find_section_page(toc, refs_pattern)
        stats.ack_page = find_section_page(toc, ack_pattern)
    return stats
