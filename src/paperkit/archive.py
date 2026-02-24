"""Submission zip creation."""

import fnmatch
import zipfile
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


def create_zip(config: PaperkitConfig) -> Path:
    """Create the submission zip archive."""
    root = config.root
    zip_name = config.zip.name or config.main
    zip_path = root / f"{zip_name}-sources.zip"

    # Remove existing
    zip_path.unlink(missing_ok=True)

    # Resolve {main} in patterns
    includes = [p.replace("{main}", config.main) for p in config.zip.include]

    # Collect files
    files: set[Path] = set()
    for pattern in includes:
        for p in _expand_pattern(root, pattern):
            if p.is_file() and not _is_excluded(p, config.zip.exclude):
                files.add(p)

    # Create zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(files):
            arcname = f.relative_to(root)
            zf.write(f, arcname)

    return zip_path


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
