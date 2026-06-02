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
_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
_MACRO_RE = re.compile(r"\\(new|renew|provide)command")


def _latex_to_plain(snippet: str) -> str | None:
    """Pipe a LaTeX snippet through pandoc and return plain text."""
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


def _flatten(main_tex: Path) -> str | None:
    """Use latexpand to resolve all \\input/\\include references."""
    if shutil.which("latexpand") is None:
        return None
    try:
        proc = subprocess.run(
            ["latexpand", str(main_tex)],
            capture_output=True,
            text=True,
            cwd=main_tex.parent,
        )
    except OSError:
        return None
    return proc.stdout or None


def _extract_macros(preamble: str) -> str:
    """Extract user-facing \\newcommand definitions from the preamble."""
    return "\n".join(
        line
        for line in preamble.splitlines()
        if _MACRO_RE.match(line.strip()) and "@" not in line
    )


def write_text_exports(config: PaperkitConfig, main: str, output_dir: Path) -> list[Path]:
    """Best-effort: write title.txt and abstract.txt alongside the PDF.

    Returns the list of files that were successfully written. Failures (missing
    latexpand, pandoc, no \\title, no abstract) are silent; callers decide
    whether to surface them.
    """
    main_tex = config.root / f"{main}.tex"
    flat = _flatten(main_tex)
    if flat is None:
        return []

    doc = re.search(r"\\begin\{document\}", flat)
    macros = _extract_macros(flat[: doc.start()] if doc else "")

    written: list[Path] = []
    for regex, filename in [(_TITLE_RE, "title.txt"), (_ABSTRACT_RE, "abstract.txt")]:
        m = regex.search(flat)
        if m is None:
            continue
        plain = _latex_to_plain(macros + "\n" + m.group(1))
        if plain:
            path = output_dir / filename
            path.write_text(plain + "\n", encoding="utf-8")
            written.append(path)

    return written


def print_text_exports(written: list[Path]) -> None:
    """Print a one-line summary of the files written, if any."""
    if not written:
        return
    names = ", ".join(p.name for p in written)
    print(f"  {_DIM}→ {names}{_RESET}")
