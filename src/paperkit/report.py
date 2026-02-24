"""Build report formatting with colors and summary table."""

import re
import subprocess

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

    proc = subprocess.run([config.engine, "--version"], capture_output=True, text=True)
    if proc.stdout:
        info["TeX Live"] = proc.stdout.splitlines()[0]

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

    # ── Detail sections ──────────────────────────────────────────────
    # Only print details for non-clean checks
    has_details = False
    for cr in check_results:
        if cr.status != CheckStatus.CLEAN or _has_extra_info(cr):
            if not has_details:
                print(_styled("  Details", _BOLD, _DIM))
                print()
                has_details = True
            _print_check_detail(cr)

    # ── Summary table ────────────────────────────────────────────────
    print(_styled("  Summary", _BOLD))
    print()

    # Environment info
    if env_info:
        for key, val in env_info.items():
            print(f"  {_styled(key.rjust(24), _DIM)}  {val}")
        print()

    # Check results table
    for cr in check_results:
        icon = _status_icon(cr.status)
        summary = _check_summary(cr)
        colored_summary = _status_colored(summary, cr.status)
        print(f"  {icon} {_styled(cr.name.rjust(24), _BOLD)}  {colored_summary}")

    print()

    # ── Overall verdict ──────────────────────────────────────────────
    worst = _worst_status(check_results)
    if worst == CheckStatus.ERROR:
        verdict = _styled("  \U0001f4a5 Build has errors", _BOLD, _RED)
    elif worst == CheckStatus.WARNING:
        verdict = _styled("  \u26a0\ufe0f  Build OK with warnings", _BOLD, _YELLOW)
    else:
        verdict = _styled("  \u2728 All checks passed", _BOLD, _GREEN)
    print(verdict)

    # Log location
    print(f"  {_styled(f"Logs: {build_result.output_dir}/*.log, *.blg", _DIM)}")
    print()


def _has_extra_info(cr: CheckResult) -> bool:
    """Check if a result has info worth showing beyond the summary."""
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


def _worst_status(results: list[CheckResult]) -> CheckStatus:
    """Return the worst status across all results."""
    if any(cr.status == CheckStatus.ERROR for cr in results):
        return CheckStatus.ERROR
    if any(cr.status == CheckStatus.WARNING for cr in results):
        return CheckStatus.WARNING
    return CheckStatus.CLEAN
