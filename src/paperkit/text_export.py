# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Extract title and abstract from LaTeX source into plain-text files.

Produces, alongside the PDF, two files inside the per-main output directory:

    out/<main>/title.txt
    out/<main>/abstract.txt

Each is a single-line, LaTeX-free string suitable for pasting into HotCRP /
EasyChair / similar submission systems. The main file's `\\input` and
`\\include` references are resolved here (papers usually keep the title and
the abstract in separate files), and stripping the remaining LaTeX is
delegated to pandoc. Every step is best-effort and never affects the build,
but a skip always says why.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from paperkit.config import PaperkitConfig

# ANSI
_DIM = "\033[2m"
_RESET = "\033[0m"

# \title{...} with one level of balanced braces in the argument.
_TITLE_RE = re.compile(r"\\title\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
_MACRO_RE = re.compile(r"\\(new|renew|provide)command")
# \input{file}, \include{file}, and \input file (no braces).
_INPUT_RE = re.compile(r"\\(?:input|include)\s*(?:\{([^{}]*)\}|([^\s{}\\]+))")
# A comment runs to the end of the line, unless the % is escaped.
_COMMENT_RE = re.compile(r"(?<!\\)%.*")


@dataclass
class TextExportResult:
    """Files written, and one line per thing that was skipped and why."""

    written: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _latex_to_plain(snippet: str) -> str | None:
    """Pipe a LaTeX snippet through pandoc and return plain text."""
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


def flatten(tex_file: Path, base: Path | None = None, _seen: set[Path] | None = None) -> str:
    """Return *tex_file* with its \\input and \\include files inlined.

    Paths resolve against *base* (the main document's directory by default),
    the way TeX resolves them however deeply nested, and get a `.tex` suffix
    when they have none. Comments are stripped first, so a commented-out
    `\\input` is not followed. Missing files and cycles are skipped: this only
    feeds the title and abstract extraction, so a partial result is useful.
    """
    root = tex_file.parent if base is None else base
    seen = set() if _seen is None else _seen
    path = tex_file.resolve()
    if path in seen or not path.is_file():
        return ""
    seen.add(path)

    out: list[str] = []
    for raw_line in path.read_text(errors="replace").splitlines():
        line = _COMMENT_RE.sub("", raw_line)
        pos = 0
        for m in _INPUT_RE.finditer(line):
            name = (m.group(1) or m.group(2) or "").strip()
            if not name:
                continue
            out.append(line[pos : m.start()])
            out.append(flatten(_resolve_input(root, name), root, seen))
            pos = m.end()
        out.append(line[pos:])
        out.append("\n")
    return "".join(out)


def _resolve_input(base: Path, name: str) -> Path:
    """Path of an \\input argument, adding .tex when the name has no suffix."""
    path = base / name
    return path if path.suffix else path.with_name(path.name + ".tex")


def _is_balanced(line: str) -> bool:
    """True if the line's braces close, ignoring escaped ones."""
    bare = line.replace("\\{", "").replace("\\}", "")
    return bare.count("{") == bare.count("}")


def _extract_macros(preamble: str) -> str:
    """User-facing \\newcommand definitions from the preamble, one per line.

    Definitions spanning several lines are left out: passing half of one to
    pandoc unbalances the snippet and it refuses the whole input.
    """
    return "\n".join(
        line
        for line in preamble.splitlines()
        if _MACRO_RE.match(line.strip()) and "@" not in line and _is_balanced(line)
    )


def write_text_exports(config: PaperkitConfig, main: str, output_dir: Path) -> TextExportResult:
    """Best-effort: write title.txt and abstract.txt alongside the PDF.

    Returns the files written plus a warning per skipped file, so the caller
    can show why nothing appeared. Never raises; the build is unaffected.
    """
    result = TextExportResult()
    main_tex = config.root / f"{main}.tex"
    if not main_tex.is_file():
        result.warnings.append(f"title.txt/abstract.txt skipped: {main}.tex not found")
        return result
    if shutil.which("pandoc") is None:
        result.warnings.append("title.txt/abstract.txt skipped: pandoc not found")
        return result

    flat = flatten(main_tex)
    doc = re.search(r"\\begin\{document\}", flat)
    macros = _extract_macros(flat[: doc.start()] if doc else "")

    for regex, filename, what in [
        (_TITLE_RE, "title.txt", "no \\title found"),
        (_ABSTRACT_RE, "abstract.txt", "no abstract found"),
    ]:
        m = regex.search(flat)
        if m is None:
            result.warnings.append(f"{filename} skipped: {what}")
            continue
        plain = _latex_to_plain(macros + "\n" + m.group(1))
        if plain is None:
            result.warnings.append(f"{filename} skipped: pandoc could not convert it")
            continue
        path = output_dir / filename
        path.write_text(plain + "\n", encoding="utf-8")
        result.written.append(path)

    return result


def print_text_exports(result: TextExportResult) -> None:
    """Print what was written and why anything was skipped."""
    if result.written:
        names = ", ".join(p.name for p in result.written)
        print(f"  {_DIM}\u2192 {names}{_RESET}")
    for warning in result.warnings:
        print(f"  {_DIM}\u2192 {warning}{_RESET}")
