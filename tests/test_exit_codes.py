# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""The exit status must agree with the verdict the report printed."""

import pytest

from paperkit.checks import CheckResult, CheckStatus
from paperkit.report import exit_code


def _result(status: CheckStatus, advisory: bool = False) -> CheckResult:
    return CheckResult(name="x", status=status, advisory=advisory)


def test_a_clean_report_succeeds() -> None:
    assert exit_code([_result(CheckStatus.CLEAN)]) == 0


def test_no_checks_at_all_succeeds() -> None:
    assert exit_code([]) == 0


@pytest.mark.parametrize("status", [CheckStatus.WARNING, CheckStatus.SKIPPED])
def test_warnings_and_skips_still_succeed(status: CheckStatus) -> None:
    # A paper with overfull boxes is still a paper you can submit, and a
    # missing tool is not the paper's fault.
    assert exit_code([_result(CheckStatus.CLEAN), _result(status)]) == 0


def test_an_error_fails() -> None:
    assert exit_code([_result(CheckStatus.CLEAN), _result(CheckStatus.ERROR)]) == 1


def test_a_missing_pdf_fails_whatever_the_checks_say() -> None:
    assert exit_code([_result(CheckStatus.CLEAN)], built=False) == 1
    assert exit_code([], built=False) == 1


def test_an_advisory_overrun_does_not_fail_the_build() -> None:
    # The page-limit check prints red without claiming the build is broken.
    assert exit_code([_result(CheckStatus.ERROR, advisory=True)]) == 0


@pytest.mark.parametrize("status", [CheckStatus.WARNING, CheckStatus.SKIPPED, CheckStatus.ERROR])
def test_strict_fails_on_anything_that_is_not_clean(status: CheckStatus) -> None:
    assert exit_code([_result(status)], strict=True) == 1


def test_strict_counts_the_page_limit_too() -> None:
    assert exit_code([_result(CheckStatus.ERROR, advisory=True)], strict=True) == 1


def test_strict_still_passes_a_clean_report() -> None:
    assert exit_code([_result(CheckStatus.CLEAN)], strict=True) == 0


@pytest.mark.parametrize("command", ["build", "check"])
def test_the_flag_is_exposed(command: str) -> None:
    from click.testing import CliRunner

    from paperkit import cli

    result = CliRunner().invoke(cli.main, [command, "--help"])
    assert "--strict" in result.output
