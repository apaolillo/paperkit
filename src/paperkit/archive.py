# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Submission zip creation."""

import datetime as dt
import fnmatch
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from paperkit import reproducible
from paperkit.config import PaperkitConfig

# Zip stores DOS timestamps, which cannot predate 1980.
_DOS_EPOCH = dt.datetime(1980, 1, 1, tzinfo=dt.UTC)


def _expand_pattern(root: Path, pattern: str) -> list[Path]:
    """Expand a glob-style include pattern relative to root.

    Supports {main} placeholder for the main .tex filename.
    """
    # Trailing / means include directory recursively
    if pattern.endswith("/"):
        d = root / pattern.rstrip("/")
        if d.is_dir():
            return sorted(d.rglob("*"))
        return []
    return sorted(root.glob(pattern))


def _is_excluded(path: Path, excludes: list[str]) -> bool:
    """Check if a path matches any exclude pattern."""
    name = path.name
    return any(fnmatch.fnmatch(name, pat) for pat in excludes)


@dataclass
class ZipResult:
    """The archive that was written, and anything the caller should be told."""

    path: Path
    warnings: list[str] = field(default_factory=list)


class MissingBblError(Exception):
    """A requested compiled bibliography is not in the build directory."""


def _bbl_entries(config: PaperkitConfig, files: set[Path]) -> tuple[dict[str, Path], list[str]]:
    """Compiled bibliographies to add, keyed by their path inside the archive.

    One per main whose .tex the archive already carries, taken from the build
    directory and stored next to that .tex, since a publisher compiling the
    archive alone looks for <main>.bbl there.
    """
    root = config.root
    entries: dict[str, Path] = {}
    warnings: list[str] = []
    missing: list[str] = []

    for main in config.mains or [config.main]:
        tex = root / f"{main}.tex"
        if tex not in files:
            continue  # this main is not part of the archive
        bbl = root / config.output_dir / main / f"{main}.bbl"
        if not bbl.is_file():
            missing.append(f"{bbl.relative_to(root)}")
            continue
        entries[f"{main}.bbl"] = bbl
        warnings += _staleness_warnings(config, main, bbl, tex)

    if missing:
        raise MissingBblError(
            "compiled bibliography not found: "
            + ", ".join(missing)
            + "; run `paperkit build` first",
        )
    return entries, warnings


def _staleness_warnings(config: PaperkitConfig, main: str, bbl: Path, tex: Path) -> list[str]:
    """Warn when the .bbl predates the sources it was compiled from."""
    warnings = []
    bbl_mtime = bbl.stat().st_mtime
    sources = [tex]
    if config.bib:
        sources.append(config.root / config.bib)
    for source in sources:
        if source.is_file() and source.stat().st_mtime > bbl_mtime:
            name = source.relative_to(config.root)
            warnings.append(
                f"{main}.bbl is older than {name}: the archive may not match the "
                f"sources, rebuild with `paperkit build`",
            )
    return warnings


def create_zip(config: PaperkitConfig, include_bbl: bool | None = None) -> ZipResult:
    """Create the submission zip archive.

    *include_bbl* overrides `[zip] include_bbl` for this run.
    """
    root = config.root
    zip_name = config.zip.name or config.main
    zip_path = root / f"{zip_name}-sources.zip"

    # Resolve {main} in patterns: expands once per main, so a single
    # "{main}.tex" entry in the zip include list pulls in every project's .tex.
    mains = config.mains or [config.main]
    includes: list[str] = []
    for include in config.zip.include:
        if "{main}" in include:
            includes.extend(include.replace("{main}", m) for m in mains)
        else:
            includes.append(include)

    # Collect files
    files: set[Path] = set()
    for pattern in includes:
        for p in _expand_pattern(root, pattern):
            if p.is_file() and not _is_excluded(p, config.zip.exclude):
                files.add(p)

    # Resolved before the old archive is removed, so a missing .bbl leaves it
    # in place. The exclude patterns do not apply: these are asked for by name.
    wanted = config.zip.include_bbl if include_bbl is None else include_bbl
    warnings: list[str] = []
    bbl_entries: dict[str, Path] = {}
    if wanted and config.is_typst:
        warnings.append("include_bbl ignored: a Typst build carries its bibliography in the PDF")
    elif wanted:
        bbl_entries, warnings = _bbl_entries(config, files)

    # Entry metadata is normalized to the build timestamp, so the same sources
    # archive to the same bytes on another machine or a fresh clone, where the
    # files' own mtimes differ.
    source_date = reproducible.resolve(config.source_date_epoch, root)
    entries = {str(f.relative_to(root)): f for f in files}
    entries.update(bbl_entries)

    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname in sorted(entries):
            zf.writestr(
                _entry_info(arcname, entries[arcname], source_date), entries[arcname].read_bytes()
            )

    return ZipResult(zip_path, warnings)


def _entry_info(
    arcname: str, source: Path, source_date: reproducible.SourceDate
) -> zipfile.ZipInfo:
    """Zip entry whose metadata depends on the sources, not on this machine.

    The timestamp is the build timestamp rather than the file's mtime (git
    does not restore mtimes, so a fresh clone would archive differently), and
    the mode keeps only the executable bit. The zip format stores DOS times,
    which start in 1980 and have two-second resolution.
    """
    stamp = max(dt.datetime.fromtimestamp(source_date.epoch, dt.UTC), _DOS_EPOCH)
    info = zipfile.ZipInfo(arcname, date_time=stamp.timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3  # Unix, whatever the host
    executable = source.stat().st_mode & 0o111
    info.external_attr = (0o755 if executable else 0o644) << 16
    return info


def print_zip_summary(zip_path: Path) -> None:
    """Print a summary of the created zip."""
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"==> Created: {zip_path}")
    print(f"    {size_mb:.1f} MiB")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

    print("")
    print("Contents:")
    for name in names[:40]:
        print(f"  {name}")
    if len(names) > 40:
        print(f"  ... ({len(names)} files total)")
    else:
        print(f"  ({len(names)} files total)")
