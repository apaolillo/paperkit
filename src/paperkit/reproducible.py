# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Byte-reproducible builds: one timestamp for every tool in the pipeline.

Three things make two builds of the same sources differ, all produced by the
PDF writer: the CreationDate/ModDate, the random tags of subsetted fonts
(e.g. "VHDZTM+Calibri"), and the trailer /ID. Setting SOURCE_DATE_EPOCH and
FORCE_SOURCE_DATE pins the first two everywhere and, from TeX Live 2024 on,
the trailer ID of xdvipdfmx too. Older xdvipdfmx, and pdfTeX at any age,
need the ID pinned explicitly; see trailer_id_code.
"""

import datetime as dt
import functools
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

EPOCH_VAR = "SOURCE_DATE_EPOCH"
FORCE_VAR = "FORCE_SOURCE_DATE"
# From this release on, xdvipdfmx derives the trailer ID from the epoch.
_EPOCH_ID_RELEASE = 2024
_TL_YEAR_RE = re.compile(r"TeX Live (\d{4})")


@dataclass(frozen=True)
class SourceDate:
    """The timestamp a build is pinned to, and where it came from."""

    epoch: int
    source: str  # "environment", "config", "git", or "current time"
    warning: str | None = None

    def __str__(self) -> str:
        stamp = dt.datetime.fromtimestamp(self.epoch, dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"{self.epoch} ({stamp}, from {self.source})"


def parse_setting(value: object) -> int | str:
    """Validate a [build] source_date_epoch setting: an int, an ISO date, or "git"."""
    if isinstance(value, bool):
        raise ValueError('[build] source_date_epoch: expected an epoch, an ISO date, or "git"')
    if isinstance(value, int):
        if value < 0:
            raise ValueError("[build] source_date_epoch: expected a non-negative epoch")
        return value
    if isinstance(value, dt.datetime):  # a bare TOML datetime
        return int(value.timestamp())
    if isinstance(value, dt.date):  # a bare TOML date
        return _from_date(value)
    if isinstance(value, str):
        if value == "git":
            return value
        try:
            return _from_iso(value)
        except ValueError:
            raise ValueError(
                f'[build] source_date_epoch: expected an epoch, an ISO date, or "git", '
                f"got {value!r}",
            ) from None
    raise ValueError('[build] source_date_epoch: expected an epoch, an ISO date, or "git"')


def _from_iso(value: str) -> int:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return int(parsed.timestamp())


def _from_date(value: dt.date) -> int:
    return int(dt.datetime.combine(value, dt.time(), tzinfo=dt.UTC).timestamp())


def git_epoch(root: Path) -> int | None:
    """Committer timestamp of HEAD, or None outside a repository."""
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=root,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def resolve(setting: int | str, root: Path) -> SourceDate:
    """Timestamp to build with. A caller's SOURCE_DATE_EPOCH wins over the config."""
    from_env = os.environ.get(EPOCH_VAR)
    if from_env and from_env.strip().isdigit():
        return SourceDate(int(from_env.strip()), "environment")

    if isinstance(setting, int):
        return SourceDate(setting, "config")

    epoch = git_epoch(root)
    if epoch is not None:
        return SourceDate(epoch, "git")
    return SourceDate(
        int(dt.datetime.now(dt.UTC).timestamp()),
        "current time",
        warning=(
            "no git commit to take a timestamp from: building with the current time, "
            "so this PDF will not be byte-identical to the next build"
        ),
    )


def build_env(source_date: SourceDate) -> dict[str, str]:
    """Environment for the LaTeX and bibliography tools."""
    return {EPOCH_VAR: str(source_date.epoch), FORCE_VAR: "1"}


@functools.lru_cache(maxsize=8)
def texlive_year(engine: str) -> int | None:
    """TeX Live release of *engine*, from its --version banner."""
    try:
        proc = subprocess.run([engine, "--version"], capture_output=True, text=True)
    except OSError:
        return None
    m = _TL_YEAR_RE.search(proc.stdout)
    return int(m.group(1)) if m else None


def needs_trailer_id(engine: str) -> bool:
    """True when the engine will not pin the trailer /ID from the epoch alone."""
    if engine == "pdflatex":
        return True  # pdfTeX never derives the ID from the epoch
    year = texlive_year(engine)
    return year is None or year < _EPOCH_ID_RELEASE


def trailer_id(source_date: SourceDate, main: str) -> str:
    """A deterministic 32 hex digit ID, distinct per main."""
    digest = hashlib.sha256(f"{source_date.epoch}:{main}".encode())
    return digest.hexdigest()[:32]


def trailer_id_code(engine: str, source_date: SourceDate, main: str) -> str:
    """TeX code pinning the trailer /ID, to prepend on the command line."""
    pdf_id = trailer_id(source_date, main)
    if engine == "pdflatex":
        return f"\\pdftrailerid{{{pdf_id}}}"
    if engine == "lualatex":
        return f"\\pdfvariable trailerid{{{pdf_id}}}"
    # xelatex writes the PDF through xdvipdfmx, which takes a special.
    return f"\\AtBeginDocument{{\\special{{pdf:trailerid [<{pdf_id}> <{pdf_id}>]}}}}"
