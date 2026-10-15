# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Submission zip creation."""

import fnmatch
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from paperkit.config import PaperkitConfig


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
    bbl_entries, warnings = _bbl_entries(config, files) if wanted else ({}, [])

    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(files):
            arcname = f.relative_to(root)
            zf.write(f, arcname)
        for arcname_str, source in sorted(bbl_entries.items()):
            zf.write(source, arcname_str)

    return ZipResult(zip_path, warnings)


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
