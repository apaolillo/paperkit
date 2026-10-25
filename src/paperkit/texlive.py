# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Upstream TeX Live: repository resolution, install-tl profile, Docker steps.

Used when `[texlive] source = "upstream"`. TeX Live is installed with
install-tl from a tlnet repository instead of the base image's texlive-*
packages. Pointing at a dated snapshot (or the frozen tlnet-final of a closed
release) makes every image rebuild install the same package set.
"""

import datetime as dt
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from paperkit.config import TexliveConfig

_SHA512_HEX = re.compile(r"[0-9a-f]{128}")

# Daily archive of the full tlnet repository.
SNAPSHOT_BASE = "https://www.texlive.info/tlnet-archive"
# TUG historic archive (first mirror listed on tug.org/historic); holds the
# frozen final repository of every closed release.
HISTORIC_BASE = "https://ftp.math.utah.edu/pub/tex/historic/systems/texlive"
# CTAN redirector to a nearby mirror of the current release. Not reproducible.
LIVE_REPOSITORY = "https://mirror.ctan.org/systems/texlive/tlnet"

# Snapshot `paperkit init` proposes: a dated repository this release was
# tested against, so a new project is reproducible without a network lookup
# at init time. Bumped per release; `paperkit texlive-update` moves a project
# to a newer one.
KNOWN_GOOD_SNAPSHOT = "2026-10-25"
KNOWN_GOOD_TLPDB_SHA512 = (
    "da7154dcba9e415aacd31e2cd6f4a75764b8c788a5c0a125109429f1ed556a3f"
    "cb8546216e1bab316594cc85f1618b0af70a7ab86d1fab2af7a5e0e211eb9f39"
)
# Enough for a typical paper: the classes publishers use, their fonts, and
# the usual maths, graphics and bibliography packages.
DEFAULT_SCHEME = "small"
DEFAULT_COLLECTIONS = (
    "latexextra",
    "fontsrecommended",
    "fontsextra",
    "publishers",
    "mathscience",
    "pictures",
    "bibtexextra",
)

# Fixed install root, so PATH does not depend on the release year.
TEXDIR = "/opt/texlive"
# Symlink to the single installed architecture's binary directory.
BIN_DIR = f"{TEXDIR}/bin/linux"

# Base image packages install-tl and the TeX tree need. python3 runs the
# latexminted helper that TeX Live ships (with its Python dependencies bundled).
APT_PREREQS = [
    "ca-certificates",
    "curl",
    "fontconfig",
    "perl",
    "python3",
    "xz-utils",
]


def resolve_repository(tl: TexliveConfig) -> str:
    """Repository URL by precedence: repository > snapshot > year > live CTAN."""
    if tl.repository:
        return tl.repository
    if tl.snapshot:
        return f"{SNAPSHOT_BASE}/{tl.snapshot.replace('-', '/')}/tlnet"
    if tl.year is not None:
        return f"{HISTORIC_BASE}/{tl.year}/tlnet-final"
    return LIVE_REPOSITORY


def is_pinned(tl: TexliveConfig) -> bool:
    """False when the package set follows the live CTAN repository."""
    return bool(tl.repository or tl.snapshot or tl.year is not None)


def describe(tl: TexliveConfig) -> str:
    """Short human-readable description of where TeX Live comes from."""
    if tl.source != "upstream":
        return "distro packages"
    if tl.repository:
        return f"upstream, {tl.repository}"
    if tl.snapshot:
        return f"upstream, snapshot {tl.snapshot}"
    if tl.year is not None:
        return f"upstream, TeX Live {tl.year} final"
    return "upstream, live CTAN (not pinned)"


# How far back to look for the newest published snapshot: the archive is
# daily, so a handful of days covers any gap in its publishing.
_SNAPSHOT_LOOKBACK_DAYS = 10
_SNAPSHOT_RE = re.compile(r"(?m)^(?P<key>\s*snapshot\s*=\s*)(?P<value>.+?)\s*$")
_TLPDB_RE = re.compile(r"(?m)^(?P<key>\s*tlpdb_sha512\s*=\s*)(?P<value>.+?)\s*$")


def snapshot_url(snapshot: str) -> str:
    return f"{SNAPSHOT_BASE}/{snapshot.replace('-', '/')}/tlnet"


def fetch_tlpdb_sha512(snapshot: str) -> str | None:
    """Checksum of a snapshot's package database, or None if it has none."""
    proc = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--max-time",
            "30",
            f"{snapshot_url(snapshot)}/tlpkg/texlive.tlpdb.sha512",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    digest = proc.stdout.split(" ", 1)[0].strip().lower()
    return digest if _SHA512_HEX.fullmatch(digest) else None


def latest_snapshot(today: dt.date | None = None) -> tuple[str, str] | None:
    """Newest published snapshot and its checksum, searching back from *today*."""
    day = today or dt.datetime.now(dt.UTC).date()
    for back in range(_SNAPSHOT_LOOKBACK_DAYS):
        candidate = (day - dt.timedelta(days=back)).isoformat()
        digest = fetch_tlpdb_sha512(candidate)
        if digest:
            return candidate, digest
    return None


def update_config_text(text: str, snapshot: str, digest: str) -> tuple[str, dict[str, str]]:
    """Rewrite the snapshot and checksum in a .paperkit.toml, keeping comments.

    Returns the new text and the replaced values, so the caller can report
    what moved. Raises ValueError when there is nothing to update.
    """
    if "[texlive]" not in text:
        raise ValueError("no [texlive] section: run `paperkit init` or add one")
    if not _SNAPSHOT_RE.search(text):
        raise ValueError("no snapshot key in [texlive]: this project does not pin one")

    previous: dict[str, str] = {}

    def _snapshot(m: re.Match[str]) -> str:
        previous["snapshot"] = m.group("value").strip('"')
        return f'{m.group("key")}"{snapshot}"'

    def _digest(m: re.Match[str]) -> str:
        previous["tlpdb_sha512"] = m.group("value").strip('"')
        return f'{m.group("key")}"{digest}"'

    text = _SNAPSHOT_RE.sub(_snapshot, text, count=1)
    if _TLPDB_RE.search(text):
        text = _TLPDB_RE.sub(_digest, text, count=1)
    else:
        # Keep the pin next to the snapshot it belongs to.
        text = _SNAPSHOT_RE.sub(lambda m: f'{m.group(0)}\ntlpdb_sha512 = "{digest}"', text, count=1)
    return text, previous


def install_profile(tl: TexliveConfig) -> str:
    """install-tl profile for a batch install of the scheme; same config, same text.

    Collections are not listed here: install-tl treats collection lines in a
    profile as the complete selection and drops the scheme's own collections.
    They are added afterwards with tlmgr instead (see install_commands).
    """
    return (
        "\n".join(
            [
                f"selected_scheme scheme-{tl.scheme}",
                f"TEXDIR {TEXDIR}",
                f"TEXMFLOCAL {TEXDIR}/texmf-local",
                f"TEXMFSYSCONFIG {TEXDIR}/texmf-config",
                f"TEXMFSYSVAR {TEXDIR}/texmf-var",
                "TEXMFHOME ~/texmf",
                "TEXMFCONFIG ~/.texlive/texmf-config",
                "TEXMFVAR ~/.texlive/texmf-var",
                "instopt_adjustpath 0",
                "instopt_adjustrepo 0",
                "instopt_letter 0",
                "instopt_portable 0",
                "instopt_write18_restricted 1",
                "tlpdbopt_autobackup 0",
                f"tlpdbopt_install_docfiles {int(tl.docs)}",
                f"tlpdbopt_install_srcfiles {int(tl.sources)}",
            ]
        )
        + "\n"
    )


def tlmgr_packages(tl: TexliveConfig) -> list[str]:
    """Collections and packages installed with tlmgr on top of the scheme."""
    collections = [f"collection-{c}" for c in sorted(set(tl.collections))]
    return collections + sorted(set(tl.packages))


def install_commands(tl: TexliveConfig) -> list[str]:
    """Shell commands (to be joined with &&) that install TeX Live in the image."""
    repo = shlex.quote(resolve_repository(tl))
    tlmgr = f"{BIN_DIR}/tlmgr"
    profile_lines = " ".join(shlex.quote(line) for line in install_profile(tl).splitlines())

    cmds = ["cd /tmp"]
    if tl.tlpdb_sha512:
        cmds.append(
            f"got=$(curl -fsSL --retry 3 {repo}/tlpkg/texlive.tlpdb.sha512 | cut -d' ' -f1)",
        )
        cmds.append(
            f'{{ [ "$got" = {tl.tlpdb_sha512} ] || {{ '
            f'echo "paperkit: [texlive] tlpdb_sha512 mismatch for" {repo} >&2; '
            f'echo "  expected {tl.tlpdb_sha512}" >&2; '
            'echo "  got      $got" >&2; '
            'echo "  The repository changed or the pin is wrong; refusing to install." >&2; '
            "exit 1; }; }",
        )
    cmds += [
        f"curl -fsSL --retry 3 -o install-tl-unx.tar.gz {repo}/install-tl-unx.tar.gz",
        f"curl -fsSL --retry 3 -o install-tl-unx.tar.gz.sha512 {repo}/install-tl-unx.tar.gz.sha512",
        "sha512sum -c install-tl-unx.tar.gz.sha512",
        "mkdir install-tl",
        "tar xzf install-tl-unx.tar.gz -C install-tl --strip-components=1",
        f"printf '%s\\n' {profile_lines} > texlive.profile",
        f"perl install-tl/install-tl -repository {repo} -profile texlive.profile",
        f'set -- {TEXDIR}/bin/*-linux && ln -s "$1" {BIN_DIR}',
        # Keep later tlmgr calls on the same repository as the install.
        f"{tlmgr} option repository {repo}",
    ]
    extra = tlmgr_packages(tl)
    if extra:
        # Fails (exit 1) on names missing from the repository.
        cmds.append(f"{tlmgr} install {' '.join(extra)}")
    cmds.append("rm -rf /tmp/install-tl* /tmp/texlive.profile")
    return cmds


# First line of every TeX engine log, e.g.
#   This is pdfTeX, Version 3.141592653-2.6-1.40.29 (TeX Live 2026) (preloaded ...
#   This is LuaHBTeX, Version 1.24.0 (TeX Live 2026)  (format=lualatex ...
_BANNER_RE = re.compile(r"This is (\S+), Version (\S+) \(([^)]*)\)")
_TL_YEAR_RE = re.compile(r"TeX Live (\d{4})")


@dataclass(frozen=True)
class EngineBanner:
    """Engine and distribution that produced a build, from its log banner."""

    engine: str
    version: str
    distribution: str  # e.g. "TeX Live 2026", "TeX Live 2022/dev/Debian"

    def __str__(self) -> str:
        return f"{self.engine} {self.version} ({self.distribution})"

    @property
    def year(self) -> int | None:
        m = _TL_YEAR_RE.match(self.distribution)
        return int(m.group(1)) if m else None

    @property
    def is_distro_build(self) -> bool:
        """True for distribution-patched TeX Live ("TeX Live 2022/dev/Debian")."""
        return "/" in self.distribution


def parse_log_banner(line: str) -> EngineBanner | None:
    m = _BANNER_RE.match(line.strip())
    return EngineBanner(*m.groups()) if m else None


def read_log_banner(log_path: Path | None) -> EngineBanner | None:
    """Banner of the engine that wrote *log_path*, or None without a usable log."""
    if not log_path or not log_path.is_file():
        return None
    with log_path.open(errors="replace") as f:
        return parse_log_banner(f.readline())


def toolchain_mismatch(tl: TexliveConfig, banner: EngineBanner) -> str | None:
    """Why *banner* cannot come from the configured upstream TeX Live, or None.

    Only upstream configs set an expectation. A snapshot taken before a new
    release is published still serves the previous one, so its year or the
    one before is accepted.
    """
    if tl.source != "upstream":
        return None
    expected = describe(tl)
    if banner.is_distro_build:
        return f"built with {banner.distribution}, a distribution build; config expects {expected}"
    year = banner.year
    if year is None:
        return None
    if tl.year is not None and year != tl.year:
        return f"built with {banner.distribution}; config expects {expected}"
    if tl.snapshot:
        snapshot_year = dt.date.fromisoformat(tl.snapshot).year
        if year not in (snapshot_year - 1, snapshot_year):
            return f"built with {banner.distribution}; config expects {expected}"
    return None
