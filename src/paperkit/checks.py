# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Verification checks ported from build.sh."""

import contextlib
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from paperkit import pages, texlive
from paperkit.builder import BuildResult
from paperkit.config import PaperkitConfig


class CheckStatus(StrEnum):
    CLEAN = "clean"
    # Could not run (missing tool or input): not a pass, so it is shown in
    # yellow and counts like a warning in the overall verdict.
    SKIPPED = "skipped"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus = CheckStatus.CLEAN
    messages: list[str] = field(default_factory=list)
    # Advisory checks render with their own status color but are excluded from
    # the overall build verdict; useful for informational metrics (page count,
    # etc.) whose "failure" doesn't mean the build broke.
    advisory: bool = False
    # Print the messages in the report's details even when the status is clean.
    show_details: bool = False


def _collect_tex_files(config: PaperkitConfig) -> list[Path]:
    """Collect all .tex files from content_dirs + every main .tex."""
    files: list[Path] = []
    for d in config.content_dirs:
        tex_dir = config.root / d
        if tex_dir.is_dir():
            files.extend(sorted(tex_dir.rglob("*.tex")))
    for main in config.mains or [config.main]:
        main_tex = config.root / f"{main}.tex"
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
    # Biber uses "> ERROR -" instead of "!"
    errors += sum(1 for line in lines if "> ERROR -" in line)
    warnings = sum(1 for line in lines if "warning" in line.lower())
    # Biber uses "> WARN -" instead of "warning"
    warnings += sum(1 for line in lines if "> WARN -" in line)
    # Subtract false positives
    fp = sum(1 for line in lines if "Providing info/warning/error" in line)
    fp += sum(1 for line in lines if "warning$ --" in line)
    # Biber summary line "WARNINGS: N" already matched by "warning" above
    fp += sum(1 for line in lines if re.match(r".*> INFO - WARNINGS: \d+", line))
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


def _pdffonts_columns(header: str, separator: str) -> dict[str, tuple[int, int]]:
    """Map pdffonts column names to (start, end) spans.

    Spans come from the dashed separator under the header, so they follow
    whatever widths the installed poppler version prints.
    """
    columns: dict[str, tuple[int, int]] = {}
    for m in re.finditer(r"-+", separator):
        start, end = m.span()
        columns[header[start:end].strip().lower()] = (start, end)
    return columns


def _pdffonts_field(line: str, span: tuple[int, int], name_width: int) -> str:
    """Extract one column of a pdffonts row.

    A font name longer than its column pushes the rest of the row right;
    shift the span by the overflow so later columns still line up.
    """
    tokens = line.split(maxsplit=1)
    overflow = max(0, len(tokens[0]) - name_width) if tokens else 0
    start, end = span
    return line[start + overflow : end + overflow].strip()


def check_font_embedding(pdf_path: Path | None, no_type3: bool = True) -> CheckResult:
    """Check all fonts are embedded and, optionally, none are Type 3 (bitmap)."""
    result = CheckResult(name="Fonts")

    if not pdf_path or not pdf_path.is_file():
        result.status = CheckStatus.SKIPPED
        result.messages.append("Skipped (PDF not found)")
        return result

    if not shutil.which("pdffonts"):
        result.status = CheckStatus.SKIPPED
        result.messages.append("Skipped (pdffonts not found; install poppler-utils)")
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

    columns = _pdffonts_columns(lines[0], lines[1])
    if "name" not in columns or "type" not in columns or "emb" not in columns:
        result.messages.append("Unrecognized pdffonts output")
        return result
    name_width = columns["name"][1] - columns["name"][0]

    font_lines = lines[2:]  # skip header + separator
    total = len(font_lines)
    unembedded = [
        line for line in font_lines if _pdffonts_field(line, columns["emb"], name_width) != "yes"
    ]
    type3 = (
        [
            line
            for line in font_lines
            if _pdffonts_field(line, columns["type"], name_width) == "Type 3"
        ]
        if no_type3
        else []
    )

    # The first message is the one-line summary shown in the report table.
    if unembedded:
        summary = f"{len(unembedded)}/{total} NOT embedded"
    else:
        summary = f"{total}/{total} embedded"
    if type3:
        summary += f", {len(type3)} Type 3 (bitmap)"
    elif no_type3:
        summary += ", no Type 3"
    result.messages.append(summary)

    if unembedded:
        result.status = CheckStatus.ERROR
        result.messages.append("Not embedded:")
        result.messages.extend(f"  {line}" for line in unembedded)

    type3_pages: dict[str, list[int]] = {}
    if type3:
        if result.status != CheckStatus.ERROR:
            result.status = CheckStatus.WARNING
        type3_pages = _type3_pages(pdf_path, columns, name_width)
        result.messages.append("Type 3 (bitmap):")
        for line in type3:
            obj = _pdffonts_field(line, columns["object id"], name_width)
            result.messages.append(f"  {line}{_format_pages(type3_pages.get(obj, []))}")
        result.messages.append(
            "  hint: usual culprits are matplotlib figures (set pdf.fonttype: 42)"
            " and METAFONT-rendered glyphs (install cm-super or use a Type 1"
            " alternative); run pdffonts on the figure PDFs included on those pages",
        )

    report = pdf_path.with_name("fonts.txt")
    _write_font_report(report, proc.stdout, type3, type3_pages, columns, name_width)
    result.messages.append(f"Full font report: {report}")

    return result


def _type3_pages(
    pdf_path: Path,
    columns: dict[str, tuple[int, int]],
    name_width: int,
) -> dict[str, list[int]]:
    """Map each Type 3 font's object ID to the pages that use it."""
    n_pages = pages.get_total_pages(pdf_path) or 0
    found: dict[str, list[int]] = defaultdict(list)
    for page in range(1, n_pages + 1):
        proc = subprocess.run(
            ["pdffonts", "-f", str(page), "-l", str(page), str(pdf_path)],
            capture_output=True,
            text=True,
        )
        for line in proc.stdout.splitlines()[2:]:
            if _pdffonts_field(line, columns["type"], name_width) == "Type 3":
                found[_pdffonts_field(line, columns["object id"], name_width)].append(page)
    return found


def _format_pages(page_list: list[int]) -> str:
    if not page_list:
        return ""
    return f"  (p. {', '.join(map(str, page_list))})"


def _write_font_report(
    report: Path,
    pdffonts_output: str,
    type3: list[str],
    type3_pages: dict[str, list[int]],
    columns: dict[str, tuple[int, int]],
    name_width: int,
) -> None:
    """Write the full pdffonts listing plus Type 3 page locations."""
    parts = ["# pdffonts", pdffonts_output.rstrip(), ""]
    if type3:
        parts.append("# Type 3 (bitmap) fonts and the pages using them")
        for line in type3:
            obj = _pdffonts_field(line, columns["object id"], name_width)
            parts.append(f"{line}{_format_pages(type3_pages.get(obj, []))}")
        parts.append("")
    with contextlib.suppress(OSError):
        report.write_text("\n".join(parts))


def check_toolchain(config: PaperkitConfig, log_path: Path | None) -> CheckResult:
    """Check the PDF was built with the TeX Live that [texlive] configures."""
    result = CheckResult(name="Toolchain")
    banner = texlive.read_log_banner(log_path)
    if banner is None:
        result.status = CheckStatus.SKIPPED
        result.messages.append("Skipped (no engine banner in the build log)")
        return result

    mismatch = texlive.toolchain_mismatch(config.texlive, banner)
    if mismatch:
        result.status = CheckStatus.WARNING
        result.messages.append(f"PDF not built with the configured TeX Live: {mismatch}")
        result.messages.append(
            "  was it built outside the paperkit image (e.g. `paperkit build --no-docker`)?",
        )
    else:
        result.messages.append(f"{banner.distribution} ({texlive.describe(config.texlive)})")
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
                hits.append(f"  {i}: {line.decode('utf-8', errors='replace')}")
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


def check_pages(config: PaperkitConfig, build_result: BuildResult) -> CheckResult:
    """Report total pages + section start pages; flag if over the configured limits."""
    result = CheckResult(name="Pages/Limit", advisory=True)
    limits = config.page_limits

    stats = pages.gather(
        pdf_path=build_result.pdf,
        aux_path=build_result.aux,
        refs_pattern=limits.refs_pattern,
        ack_pattern=limits.ack_pattern,
        ack_counts_as_content=limits.ack_counts_as_content,
    )

    if stats.total is None:
        result.status = CheckStatus.SKIPPED
        result.messages.append("Skipped (pdfinfo not found or no PDF)")
        return result

    # Inline summary string + per-metric overage report.
    parts: list[str] = []
    overages: list[str] = []

    def _metric(label: str, value: int | None, limit: int | None, suffix: str = "") -> None:
        if value is None:
            return
        if limit is None:
            parts.append(f"{label} {value}{suffix}")
        else:
            if value > limit:
                parts.append(f"{label} {value}/{limit}{suffix} \u274c")
                overages.append(f"{label}: {value} > {limit}")
            else:
                parts.append(f"{label} {value}/{limit}{suffix} \u2714")

    _metric("total", stats.total, limits.total)

    refs_note = f"refs start p.{stats.refs_page}" if stats.refs_page is not None else ""
    if limits.ack_counts_as_content and stats.ack_page is not None:
        # Say why the acknowledgments are inside the budget.
        refs_note = f"{refs_note}; acks counted" if refs_note else "acks counted"
    _metric(
        "before refs",
        stats.before_refs,
        limits.before_refs,
        f" ({refs_note})" if refs_note else "",
    )

    _metric(
        "before ack",
        stats.before_ack,
        limits.before_ack,
        f" (ack starts p.{stats.ack_page})" if stats.ack_page is not None else "",
    )

    # Note un-detected milestones only when the user has set a limit for them.
    if limits.before_refs is not None and stats.before_refs is None:
        parts.append("refs not detected")
    if limits.before_ack is not None and stats.before_ack is None:
        parts.append("ack not detected")

    summary = " \u2502 ".join(parts) if parts else "no data"
    if overages:
        result.status = CheckStatus.ERROR
        result.messages.append(summary)
        for line in overages:
            result.messages.append(f"  {line}")
    else:
        result.messages.append(summary)

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
        result.status = CheckStatus.SKIPPED
        result.messages.append("Skipped (bibtex-tidy not found)")
        return result

    # Report version
    ver_proc = subprocess.run(["bibtex-tidy", "--version"], capture_output=True, text=True)
    version = ver_proc.stdout.strip() or "unknown"
    result.messages.append(f"bibtex-tidy: {version}")

    from paperkit.profiles import get_profile

    profile = get_profile(config)
    tidy_args = profile.bibtex_tidy_args(sort=config.checks.bibtex_tidy.sort)

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
                result.messages.append(f"  {line.replace('DUPLICATE_ENTRY: ', '')}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return result


def run_all_checks(
    config: PaperkitConfig,
    build_result: BuildResult,
    bib_results: list[CheckResult] | None = None,
) -> list[CheckResult]:
    """Run all enabled per-target checks and return results.

    Bibliography checks span targets sharing a bib file, so the caller
    computes them (paperkit.bibliography) and passes them in *bib_results*.
    """
    results: list[CheckResult] = []

    # Log checks (always run)
    if build_result.log:
        results.append(check_log_errors(build_result.log, "LaTeX"))
    if build_result.blg:
        bib_label = "Biber" if config.biber else "BibTeX"
        results.append(check_log_errors(build_result.blg, bib_label))

    if config.texlive.source == "upstream":
        results.append(check_toolchain(config, build_result.log))

    if config.checks.overfull_boxes:
        results.append(check_overfull_boxes(build_result.log))

    if config.checks.font_embedding:
        results.append(check_font_embedding(build_result.pdf, config.checks.no_type3))

    if config.checks.non_ascii:
        results.append(check_non_ascii(config))

    if config.checks.trailing_whitespace:
        results.append(check_trailing_whitespace(config))

    if config.checks.final_newline:
        results.append(check_final_newline(config))

    results += bib_results or []

    results.append(check_pages(config, build_result))

    return results
