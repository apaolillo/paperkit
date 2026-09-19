"""Upstream TeX Live: repository resolution, install-tl profile, Docker steps.

Used when `[texlive] source = "upstream"`. TeX Live is installed with
install-tl from a tlnet repository instead of the base image's texlive-*
packages. Pointing at a dated snapshot (or the frozen tlnet-final of a closed
release) makes every image rebuild install the same package set.
"""

import shlex

from paperkit.config import TexliveConfig

# Daily archive of the full tlnet repository.
SNAPSHOT_BASE = "https://www.texlive.info/tlnet-archive"
# TUG historic archive (first mirror listed on tug.org/historic); holds the
# frozen final repository of every closed release.
HISTORIC_BASE = "https://ftp.math.utah.edu/pub/tex/historic/systems/texlive"
# CTAN redirector to a nearby mirror of the current release. Not reproducible.
LIVE_REPOSITORY = "https://mirror.ctan.org/systems/texlive/tlnet"

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


def install_profile(tl: TexliveConfig) -> str:
    """install-tl profile for a batch install of the scheme; same config, same text.

    Collections are not listed here: install-tl treats collection lines in a
    profile as the complete selection and drops the scheme's own collections.
    They are added afterwards with tlmgr instead (see install_commands).
    """
    return "\n".join([
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
    ]) + "\n"


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
