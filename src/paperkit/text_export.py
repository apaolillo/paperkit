"""Extract title and abstract from LaTeX source into plain-text files.

Produces, alongside the PDF, two files inside the per-main output directory:

    out/<main>/title.txt
    out/<main>/abstract.txt

Each is a single-line, LaTeX-free string suitable for pasting into HotCRP /
EasyChair / similar submission systems. Stripping is delegated to pandoc; if
pandoc is not available on the host the export is skipped with a warning and
the build is not affected.
"""

import re
import shutil
import subprocess
from pathlib import Path

from paperkit.config import PaperkitConfig

# ANSI
_DIM = "\033[2m"
_RESET = "\033[0m"

# \title{...} with one level of balanced braces in the argument.
_TITLE_RE = re.compile(r"\\title\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
# \begin{abstract} ... \end{abstract}, multiline.
_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)


def _latex_to_plain(snippet: str) -> str | None:
    """Pipe a LaTeX snippet through pandoc and return single-line plain text.

    Returns None if pandoc fails (missing binary, conversion error, ...).
    """
    if shutil.which("pandoc") is None:
        return None
    try:
        proc = subprocess.run(
            ["pandoc", "-f", "latex", "-t", "plain", "--wrap=none"],
            input=snippet,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    return proc.stdout.strip() or None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def extract_title(main_tex: Path) -> str | None:
    """Return the plain-text title of *main_tex*, or None if not found."""
    src = _read_text(main_tex)
    if src is None:
        return None
    m = _TITLE_RE.search(src)
    if m is None:
        return None
    return _latex_to_plain(m.group(1))


def extract_abstract(main_tex: Path, content_dirs: list[Path]) -> str | None:
    """Locate the abstract by scanning main_tex and content_dirs, return plain text."""
    # main.tex itself first (handles inline abstracts)
    candidates: list[Path] = [main_tex]
    for d in content_dirs:
        if d.is_dir():
            candidates.extend(sorted(d.rglob("*.tex")))

    seen: set[Path] = set()
    for tex in candidates:
        if tex in seen:
            continue
        seen.add(tex)
        src = _read_text(tex)
        if src is None:
            continue
        m = _ABSTRACT_RE.search(src)
        if m is None:
            continue
        return _latex_to_plain(m.group(1))
    return None


def write_text_exports(config: PaperkitConfig, main: str, output_dir: Path) -> list[Path]:
    """Best-effort: write title.txt and abstract.txt alongside the PDF.

    Returns the list of files that were successfully written. Failures (missing
    pandoc, no \\title, no abstract) are silent at the function level; callers
    decide whether to surface them.
    """
    written: list[Path] = []
    main_tex = config.root / f"{main}.tex"
    content_dirs = [config.root / d for d in config.content_dirs]

    title = extract_title(main_tex)
    if title:
        title_path = output_dir / "title.txt"
        title_path.write_text(title + "\n", encoding="utf-8")
        written.append(title_path)

    abstract = extract_abstract(main_tex, content_dirs)
    if abstract:
        abstract_path = output_dir / "abstract.txt"
        abstract_path.write_text(abstract + "\n", encoding="utf-8")
        written.append(abstract_path)

    return written


def print_text_exports(written: list[Path]) -> None:
    """Print a one-line summary of the files written, if any."""
    if not written:
        return
    names = ", ".join(p.name for p in written)
    print(f"  {_DIM}→ {names}{_RESET}")
