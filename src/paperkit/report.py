# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Build report formatting with colors and summary table."""

import re
import shutil
import subprocess

from paperkit import reproducible, texlive
from paperkit.builder import BuildResult
from paperkit.checks import CheckResult, CheckStatus
from paperkit.config import PaperkitConfig

# ANSI color codes
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_WHITE = "\033[37m"

# Status decorations
_STATUS_STYLE: dict[CheckStatus, tuple[str, str, str]] = {
    #                     emoji   color    label
    CheckStatus.CLEAN: ("\u2705", _GREEN, "pass"),
    CheckStatus.SKIPPED: ("\u23ed\ufe0f ", _YELLOW, "skip"),
    CheckStatus.WARNING: ("\u26a0\ufe0f ", _YELLOW, "warn"),
    CheckStatus.ERROR: ("\u274c", _RED, "FAIL"),
}


def _styled(text: str, *codes: str) -> str:
    return "".join(codes) + text + _RESET


def _status_icon(status: CheckStatus) -> str:
    emoji, _, _ = _STATUS_STYLE[status]
    return emoji


def _status_colored(text: str, status: CheckStatus) -> str:
    _, color, _ = _STATUS_STYLE[status]
    return _styled(text, color)


def get_environment_info(config: PaperkitConfig, build_result: BuildResult) -> dict[str, str]:
    """Collect environment info as a dict."""
    info: dict[str, str] = {}

    # The log banner names the engine that produced the PDF, wherever this
    # report runs; probing the engine on PATH is only a fallback.
    banner = texlive.read_log_banner(build_result.log)
    if banner:
        info["TeX Live"] = str(banner)
    elif shutil.which(config.engine):
        proc = subprocess.run([config.engine, "--version"], capture_output=True, text=True)
        if proc.stdout:
            first = proc.stdout.splitlines()[0]
            info["TeX Live"] = f"{first} (host {config.engine}, no build log)"
    if config.texlive.source == "upstream":
        info["TeX Live source"] = texlive.describe(config.texlive)
    info["Source date"] = str(reproducible.resolve(config.source_date_epoch, config.root))

    if config.profile_name == "acm" and build_result.log and build_result.log.is_file():
        text = build_result.log.read_text(errors="replace")
        m = re.search(r"acmart (\d{4}/\d{2}/\d{2} v[\d.]+)", text)
        info["acmart"] = m.group(1) if m else "not found"

    return info


def print_report(
    build_result: BuildResult,
    check_results: list[CheckResult],
    env_info: dict[str, str] | None = None,
) -> None:
    """Print formatted build report with colors and summary table."""
    print()

    # -- Detail sections --
    _print_details(check_results)

    # -- Summary table --
    print(_styled("  Summary", _BOLD))
    print()

    # Environment info
    if env_info:
        for key, val in env_info.items():
            print(f"  {_styled(key.rjust(24), _DIM)}  {val}")
        print()

    _print_rows(check_results)
    print()

    # -- Overall verdict --
    worst = _worst_status(check_results)
    if worst == CheckStatus.ERROR:
        verdict = _styled("  \U0001f4a5 Build has errors", _BOLD, _RED)
    elif worst == CheckStatus.WARNING:
        verdict = _styled("  \u26a0\ufe0f  Build OK with warnings", _BOLD, _YELLOW)
    else:
        verdict = _styled("  \u2728 All checks passed", _BOLD, _GREEN)
    print(verdict)

    # Log location
    print(f"  {_styled(f'Logs: {build_result.output_dir}/*.log, *.blg', _DIM)}")
    print()


def _print_details(check_results: list[CheckResult]) -> None:
    """Detail sections for non-clean checks (and clean ones with extra info)."""
    has_details = False
    for cr in check_results:
        if cr.status != CheckStatus.CLEAN or _has_extra_info(cr):
            if not has_details:
                print(_styled("  Details", _BOLD, _DIM))
                print()
                has_details = True
            _print_check_detail(cr)


def _print_rows(check_results: list[CheckResult]) -> None:
    """One summary row per check."""
    for cr in check_results:
        icon = _status_icon(cr.status)
        colored_summary = _status_colored(_check_summary(cr), cr.status)
        print(f"  {icon} {_styled(cr.name.rjust(24), _BOLD)}  {colored_summary}")


def _has_extra_info(cr: CheckResult) -> bool:
    """Check if a result has info worth showing beyond the summary."""
    if cr.show_details:
        return True
    # bibtex-tidy reports version in messages even when clean
    return cr.name == "BibTeX tidy" and any("bibtex-tidy:" in m for m in cr.messages)


def _check_summary(cr: CheckResult) -> str:
    """One-line summary for the table."""
    if not cr.messages:
        return cr.status.value
    # Use first message as summary, strip leading whitespace
    return cr.messages[0].strip()


def _print_check_detail(cr: CheckResult) -> None:
    """Print detailed messages for a check (warnings/errors)."""
    icon = _status_icon(cr.status)
    _, color, _ = _STATUS_STYLE[cr.status]
    print(f"  {icon} {_styled(cr.name, _BOLD, color)}")
    for msg in cr.messages:
        print(f"     {_status_colored(msg, cr.status)}")
    print()


# Statuses that make the overall verdict a warning.
_WARNING_LEVEL = (CheckStatus.WARNING, CheckStatus.SKIPPED)


def _worst_status(results: list[CheckResult], strict: bool = False) -> CheckStatus:
    """Worst verdict across results (CLEAN, WARNING or ERROR).

    Advisory results are excluded, so a paper over its page limit is shown in
    red without turning the build into a failure, unless *strict* asks for
    everything to count.
    """
    binding = results if strict else [cr for cr in results if not cr.advisory]
    if any(cr.status == CheckStatus.ERROR for cr in binding):
        return CheckStatus.ERROR
    if any(cr.status in _WARNING_LEVEL for cr in binding):
        return CheckStatus.WARNING
    return CheckStatus.CLEAN


def exit_code(results: list[CheckResult], strict: bool = False, built: bool = True) -> int:
    """The process exit status the report justifies.

    1 when the report says the build has errors, or when no PDF was produced,
    so a script sees what the reader sees. Warnings are a 0: a paper with
    three overfull boxes is still a paper you can submit. With *strict* every
    warning, skipped check and page-limit overrun counts as a failure too,
    which is what a paper repository's own CI usually wants.
    """
    if not built:
        return 1
    worst = _worst_status(results, strict=strict)
    if worst == CheckStatus.ERROR:
        return 1
    return 1 if strict and worst == CheckStatus.WARNING else 0


def print_multi_summary(
    runs: list[tuple[str, BuildResult, list[CheckResult]]],
    shared: list[CheckResult] | None = None,
) -> None:
    """Print a one-line-per-main summary across all builds.

    *shared* holds project-wide results (bibliography checks, one per bib
    file), printed once in their own block and included in the verdict.
    """
    if shared:
        print(_styled("  Bibliography", _BOLD))
        print()
        _print_details(shared)
        _print_rows(shared)
        print()

    print(_styled("  Per-project summary", _BOLD))
    print()

    width = max(len(name) for name, _, _ in runs) if runs else 0
    counts = {CheckStatus.CLEAN: 0, CheckStatus.WARNING: 0, CheckStatus.ERROR: 0}
    failed = 0

    for name, build_result, check_results in runs:
        if not build_result.success:
            failed += 1
            counts[CheckStatus.ERROR] += 1
            icon = _status_icon(CheckStatus.ERROR)
            label = _status_colored("build failed", CheckStatus.ERROR)
        else:
            worst = _worst_status(check_results)
            counts[worst] += 1
            icon = _status_icon(worst)
            if worst == CheckStatus.CLEAN:
                label = _status_colored("all checks passed", worst)
            else:
                level = _WARNING_LEVEL if worst == CheckStatus.WARNING else (worst,)
                bad = [cr.name for cr in check_results if cr.status in level]
                summary = ", ".join(bad) if bad else worst.value
                label = _status_colored(summary, worst)
        print(f"  {icon} {_styled(name.ljust(width), _BOLD)}  {label}")

    print()
    n = len(runs)
    parts = [
        f"{counts[CheckStatus.CLEAN]} pass",
        f"{counts[CheckStatus.WARNING]} warn",
        f"{counts[CheckStatus.ERROR]} fail",
    ]
    breakdown = ", ".join(parts)
    shared_worst = _worst_status(shared or [])
    if shared_worst != CheckStatus.CLEAN:
        breakdown += f"; bibliography: {_STATUS_STYLE[shared_worst][2]}"
    if failed:
        verdict = _styled(
            f"  \U0001f4a5 {failed}/{n} project(s) failed to build  ({breakdown})",
            _BOLD,
            _RED,
        )
    elif counts[CheckStatus.WARNING] or shared_worst != CheckStatus.CLEAN:
        verdict = _styled(
            f"  \u26a0\ufe0f  {n} project(s) built, see warnings  ({breakdown})",
            _BOLD,
            _YELLOW,
        )
    else:
        verdict = _styled(
            f"  \u2728 All {n} project(s) clean  ({breakdown})",
            _BOLD,
            _GREEN,
        )
    print(verdict)
    print()
