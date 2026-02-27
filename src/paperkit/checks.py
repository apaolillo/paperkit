"""Verification checks ported from build.sh."""

import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from paperkit.builder import BuildResult
from paperkit.config import PaperkitConfig


class CheckStatus(StrEnum):
    CLEAN = "clean"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus = CheckStatus.CLEAN
    messages: list[str] = field(default_factory=list)


def _collect_tex_files(config: PaperkitConfig) -> list[Path]:
    """Collect all .tex files from content_dirs + main .tex."""
    files: list[Path] = []
    for d in config.content_dirs:
        tex_dir = config.root / d
        if tex_dir.is_dir():
            files.extend(sorted(tex_dir.glob("*.tex")))
    main_tex = config.root / f"{config.main}.tex"
    if main_tex.is_file():
        files.append(main_tex)
    return files


def check_log_errors(log_path: Path, label: str) -> CheckResult:
    """Parse a LaTeX or BibTeX log for errors and warnings."""
    result = CheckResult(name=label)
    if not log_path.is_file():
        return result

    text = log_path.read_text(errors="replace")
    lines = text.splitlines()

    errors = sum(1 for line in lines if line.startswith("!"))
    warnings = sum(1 for line in lines if "warning" in line.lower())
    # Subtract false positives
    fp = sum(1 for line in lines if "Providing info/warning/error" in line)
    fp += sum(1 for line in lines if "warning$ --" in line)
    warnings = max(0, warnings - fp)

    if errors > 0:
        result.status = CheckStatus.ERROR
        result.messages.append(f"{errors} error(s), {warnings} warning(s)")
        # Group errors with line numbers
        err_info: dict[str, list[int]] = defaultdict(list)
        prev_err = None
        for line in lines:
            if line.startswith("!"):
                prev_err = line
            elif prev_err and line.startswith("l."):
                m = re.match(r"l\.(\d+)", line)
                if m:
                    err_info[prev_err].append(int(m.group(1)))
                prev_err = None
            else:
                prev_err = None
        for err, lnums in sorted(err_info.items(), key=lambda x: -len(x[1])):
            lo, hi = min(lnums), max(lnums)
            loc = f"l.{lo}" if lo == hi else f"l.{lo}-{hi}"
            result.messages.append(f"  {len(lnums):4d} {err} ({loc})")
    elif warnings > 0:
        result.status = CheckStatus.WARNING
        result.messages.append(f"{warnings} warning(s)")
    else:
        result.messages.append("clean")

    return result


def check_overfull_boxes(log_path: Path | None) -> CheckResult:
    """Count overfull and underfull boxes from the LaTeX log."""
    result = CheckResult(name="Boxes")
    if not log_path or not log_path.is_file():
        return result

    text = log_path.read_text(errors="replace")
    lines = text.splitlines()

    overfull = [line for line in lines if line.startswith("Overfull")]
    underfull_count = sum(1 for line in lines if line.startswith("Underfull"))

    if overfull or underfull_count:
        result.status = CheckStatus.WARNING
        result.messages.append(f"{len(overfull)} overfull, {underfull_count} underfull")
        for line in overfull:
            result.messages.append(f"  {line}")
    else:
        result.messages.append("clean")

    return result


def check_font_embedding(pdf_path: Path | None) -> CheckResult:
    """Check all fonts are embedded using pdffonts."""
    result = CheckResult(name="Fonts")

    if not pdf_path or not pdf_path.is_file():
        result.messages.append("PDF not found")
        return result

    if not shutil.which("pdffonts"):
        result.messages.append("pdffonts not found (install poppler-utils)")
        return result

    proc = subprocess.run(
        ["pdffonts", str(pdf_path)],
        capture_output=True,
        text=True,
    )
    lines = proc.stdout.strip().splitlines()
    if len(lines) < 3:
        result.messages.append("No fonts found")
        return result

    font_lines = lines[2:]  # skip header + separator
    total = len(font_lines)
    not_embedded = sum(1 for line in font_lines if len(line) >= 75 and line[72:75].strip() != "yes")

    if not_embedded == 0:
        result.messages.append(f"{total}/{total} embedded")
    else:
        result.status = CheckStatus.ERROR
        result.messages.append(f"{not_embedded}/{total} NOT embedded")
        for line in font_lines:
            if len(line) >= 75 and line[72:75].strip() != "yes":
                result.messages.append(f"  {line}")

    return result


def check_non_ascii(config: PaperkitConfig) -> CheckResult:
    """Flag non-ASCII characters in source .tex files."""
    result = CheckResult(name="Non-ASCII")
    tex_files = _collect_tex_files(config)
    bad_files: list[tuple[str, list[str]]] = []

    for tf in tex_files:
        content = tf.read_bytes()
        hits = []
        for i, line in enumerate(content.splitlines(), 1):
            if any(b > 127 for b in line):
                hits.append(f"  {i}: {line.decode("utf-8", errors="replace")}")
        if hits:
            rel = tf.relative_to(config.root)
            bad_files.append((str(rel), hits))

    if not bad_files:
        result.messages.append("All source .tex files are ASCII-clean")
    else:
        result.status = CheckStatus.WARNING
        for relpath, hits in bad_files:
            result.messages.append(f"{relpath}:")
            result.messages.extend(hits)

    return result


def check_trailing_whitespace(config: PaperkitConfig) -> CheckResult:
    """Check for trailing whitespace in source .tex files."""
    result = CheckResult(name="Trailing whitespace")
    tex_files = _collect_tex_files(config)
    total = 0
    file_counts: list[tuple[str, int]] = []

    for tf in tex_files:
        text = tf.read_text(errors="replace")
        count = sum(1 for line in text.splitlines() if line != line.rstrip(" "))
        if count:
            rel = tf.relative_to(config.root)
            file_counts.append((str(rel), count))
            total += count

    if total == 0:
        result.messages.append("No trailing whitespace found")
    else:
        result.status = CheckStatus.WARNING
        result.messages.append(f"{total} line(s) with trailing whitespace:")
        for relpath, count in file_counts:
            result.messages.append(f"  {relpath} ({count} lines)")

    return result


def check_final_newline(config: PaperkitConfig) -> CheckResult:
    """Check that each .tex file ends with exactly one newline."""
    result = CheckResult(name="Final newline")
    tex_files = _collect_tex_files(config)
    issues: list[str] = []

    for tf in tex_files:
        data = tf.read_bytes()
        rel = str(tf.relative_to(config.root))
        if not data:
            issues.append(f"{rel}: empty file")
        elif data[-1:] != b"\n":
            issues.append(f"{rel}: no final newline")
        elif data[-2:] == b"\n\n":
            issues.append(f"{rel}: multiple trailing newlines")

    if not issues:
        result.messages.append("All source .tex files end with a single newline")
    else:
        result.status = CheckStatus.WARNING
        result.messages.extend(issues)

    return result


def check_unused_bib(config: PaperkitConfig, aux_path: Path | None) -> CheckResult:
    """Find bib entries that are defined but never cited."""
    result = CheckResult(name="Unused bib entries")
    bib_path = config.root / config.bib if config.bib else None

    if not aux_path or not aux_path.is_file() or not bib_path or not bib_path.is_file():
        result.messages.append("Skipped (aux or bib file not found)")
        return result

    # Extract cited keys from .aux
    # bibtex uses \citation{key1,key2}, biblatex/biber uses \abx@aux@cite{N}{key}
    aux_text = aux_path.read_text(errors="replace")
    cited: set[str] = set()
    for m in re.finditer(r"\\citation\{([^}]+)\}", aux_text):
        cited.update(m.group(1).split(","))
    for m in re.finditer(r"\\abx@aux@cite\{[^}]*\}\{([^}]+)\}", aux_text):
        cited.add(m.group(1))

    # Extract defined keys from .bib
    bib_text = bib_path.read_text(errors="replace")
    defined: set[str] = set()
    for m in re.finditer(r"^\s*@\w+\{([^,]+)", bib_text, re.MULTILINE):
        defined.add(m.group(1).strip())

    unused = sorted(defined - cited)
    if not unused:
        result.messages.append("All bib entries are cited")
    else:
        result.status = CheckStatus.WARNING
        result.messages.append(f"{len(unused)} unused bib entry/entries:")
        for key in unused:
            result.messages.append(f"  {key}")

    return result


def check_bibtex_tidy(config: PaperkitConfig) -> CheckResult:
    """Run bibtex-tidy in dry-run mode and check for differences."""
    result = CheckResult(name="BibTeX tidy")

    if not config.checks.bibtex_tidy.enabled:
        result.messages.append("Disabled")
        return result

    bib_path = config.root / config.bib if config.bib else None
    if not bib_path or not bib_path.is_file():
        result.messages.append("Skipped (bib file not found)")
        return result

    if not shutil.which("bibtex-tidy"):
        result.messages.append("Skipped (bibtex-tidy not found)")
        return result

    # Report version
    ver_proc = subprocess.run(["bibtex-tidy", "--version"], capture_output=True, text=True)
    version = ver_proc.stdout.strip() or "unknown"
    result.messages.append(f"bibtex-tidy: {version}")

    from paperkit.profiles import get_profile

    profile = get_profile(config)
    tidy_args = profile.bibtex_tidy_args()

    # Copy bib to temp, run bibtex-tidy, compare
    with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False) as tmp:
        tmp.write(bib_path.read_text())
        tmp_path = Path(tmp.name)

    try:
        tidy_proc = subprocess.run(
            ["bibtex-tidy", *tidy_args, str(tmp_path)],
            capture_output=True,
            text=True,
        )

        # Compare
        original = bib_path.read_text()
        tidied = tmp_path.read_text()

        if original == tidied:
            result.messages.append("references.bib is tidy")
        else:
            orig_lines = original.splitlines()
            tidy_lines = tidied.splitlines()
            diff_lines = sum(1 for a, b in zip(orig_lines, tidy_lines, strict=False) if a != b)
            result.status = CheckStatus.WARNING
            result.messages.append(f"references.bib is not tidy ({diff_lines} lines differ)")
            cmd = " ".join(["bibtex-tidy", *tidy_args])
            result.messages.append(f"To fix, run: {cmd} {config.bib}")

        # Check for duplicates
        for line in tidy_proc.stdout.splitlines():
            if "DUPLICATE_ENTRY" in line:
                result.status = CheckStatus.WARNING
                result.messages.append(f"  {line.replace("DUPLICATE_ENTRY: ", "")}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return result


def run_all_checks(config: PaperkitConfig, build_result: BuildResult) -> list[CheckResult]:
    """Run all enabled checks and return results."""
    results: list[CheckResult] = []

    # Log checks (always run)
    if build_result.log:
        results.append(check_log_errors(build_result.log, "LaTeX"))
    if build_result.blg:
        bib_label = "Biber" if config.biber else "BibTeX"
        results.append(check_log_errors(build_result.blg, bib_label))

    if config.checks.overfull_boxes:
        results.append(check_overfull_boxes(build_result.log))

    if config.checks.font_embedding:
        results.append(check_font_embedding(build_result.pdf))

    if config.checks.non_ascii:
        results.append(check_non_ascii(config))

    if config.checks.trailing_whitespace:
        results.append(check_trailing_whitespace(config))

    if config.checks.final_newline:
        results.append(check_final_newline(config))

    if config.checks.unused_bib:
        results.append(check_unused_bib(config, build_result.aux))

    if config.checks.bibtex_tidy.enabled:
        results.append(check_bibtex_tidy(config))

    return results
