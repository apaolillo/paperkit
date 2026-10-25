# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Typst as a build engine: the pinned release, how it is installed, its banner.

Typst publishes one static binary per release. paperkit pins a version and
the sha256 of its tarball per architecture, so an image gets exactly one
known compiler, the way [texlive] pins a snapshot by its package database
checksum. Building from source with cargo is available for a version that
has no release binary, pinned to the same tag.
"""

import platform
import re
import shlex
from dataclasses import dataclass, field

# The current release when this paperkit was released; bump per release
# after a fixture build.
KNOWN_GOOD_VERSION = "0.15.1"
KNOWN_GOOD_SHA256 = {
    "x86_64": "a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c",
    "aarch64": "5aa8d74a3d906e60ea12a66ac2f37f8eef1b14cbad7182a745e393a10c23dcee",
}

RELEASES = "https://github.com/typst/typst/releases/download"
# Where the image keeps declared packages and its own cache; both are set as
# environment variables typst reads (TYPST_PACKAGE_PATH, TYPST_PACKAGE_CACHE_PATH).
PACKAGE_PATH = "/opt/typst/packages"
PACKAGE_CACHE_PATH = "/opt/typst/cache"
BIN_DIR = "/usr/local/bin"

_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
_PACKAGE_RE = re.compile(
    r"@(?P<namespace>[a-z0-9-]+)/(?P<name>[a-z0-9-]+):(?P<version>\d+\.\d+\.\d+)"
)
_BANNER_RE = re.compile(r"^typst (?P<version>\d+\.\d+\.\d+)")
# A package file as a dependency list names it: under a package root
# (<root>/<namespace>/<name>/<version>/...), or as the virtual path typst
# prints in diagnostics (@<namespace>/<name>:<version>/...).
_DEPS_PACKAGE_RE = re.compile(
    r"(?:^|/)(?P<namespace>[a-z0-9-]+)/(?P<name>[a-z0-9-]+)/(?P<version>\d+\.\d+\.\d+)/"
)
_DEPS_VIRTUAL_RE = re.compile(
    r"^@(?P<namespace>[a-z0-9-]+)/(?P<name>[a-z0-9-]+):(?P<version>\d+\.\d+\.\d+)/"
)
_PACKAGE_ROOT_MARKERS = (PACKAGE_PATH + "/", PACKAGE_CACHE_PATH + "/", "/typst/packages/")

_ARCHES = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}


def host_arch() -> str:
    """The release architecture of this machine, which is what Docker builds for."""
    machine = platform.machine().lower()
    try:
        return _ARCHES[machine]
    except KeyError:
        raise ValueError(f"no typst release for this architecture: {machine!r}") from None


def packages_from_deps(inputs: list[str]) -> set[str]:
    """The package specs among a compilation's inputs, from where they were read."""
    found = set()
    for raw in inputs:
        path = raw.replace("\\", "/")
        m = _DEPS_VIRTUAL_RE.match(path)
        if m is None:
            root = next((r for r in _PACKAGE_ROOT_MARKERS if r in path), None)
            if root is None:
                continue
            m = _DEPS_PACKAGE_RE.search(path[path.index(root) + len(root) - 1 :])
        if m:
            found.add(f"@{m['namespace']}/{m['name']}:{m['version']}")
    return found


@dataclass
class TypstConfig:
    # Release to install in the image; the default is verified per paperkit release.
    version: str = KNOWN_GOOD_VERSION
    # sha256 of the release tarball for this machine's architecture. Known for
    # the default version; required for any other, unless building from source.
    sha256: str | None = None
    # `cargo install --locked typst-cli` pinned to the version's tag, instead
    # of the release binary: slower and needs a Rust toolchain in the image.
    build_from_source: bool = False
    # Directories of fonts, relative to the root, passed with --font-path.
    fonts: list[str] = field(default_factory=list)
    # Typst searches the system's fonts by default and substitutes silently
    # when a family is missing, which makes a build depend on the machine.
    # Off by default: the embedded fonts and `fonts` are what a build sees.
    ignore_system_fonts: bool = True
    # Universe packages, as imported ("@preview/charged-ieee:0.1.4"),
    # downloaded into the image when it is built so builds need no network.
    packages: list[str] = field(default_factory=list)
    # A local packages tree on the host (namespaces as subdirectories, as in
    # ~/.local/share/typst/packages), mounted read-only into the container.
    packages_dir: str | None = None
    # One of typst's --pdf-standard values, for venues that require PDF/A.
    pdf_standard: str | None = None
    # Anything else to pass to `typst compile`, verbatim.
    extra_args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Package:
    namespace: str
    name: str
    version: str

    @property
    def spec(self) -> str:
        return f"@{self.namespace}/{self.name}:{self.version}"


def parse_package(spec: str) -> Package:
    """A package as it is imported, "@namespace/name:version"."""
    m = _PACKAGE_RE.fullmatch(spec.strip())
    if not m:
        raise ValueError(
            f'[typst] packages: expected "@namespace/name:X.Y.Z", got {spec!r}',
        )
    return Package(m["namespace"], m["name"], m["version"])


def release_url(version: str, arch: str) -> str:
    return f"{RELEASES}/v{version}/typst-{arch}-unknown-linux-musl.tar.xz"


def expected_sha256(tc: TypstConfig, arch: str) -> str:
    """The checksum the install verifies, or an error when nothing pins it."""
    if tc.sha256:
        return tc.sha256
    known = KNOWN_GOOD_SHA256.get(arch) if tc.version == KNOWN_GOOD_VERSION else None
    if not known:
        raise ValueError(
            f"[typst] sha256: no known checksum for typst {tc.version} on {arch}; set it "
            f"(sha256 of {release_url(tc.version, arch)}) or set build_from_source = true",
        )
    return known


def install_commands(tc: TypstConfig, arch: str) -> list[str]:
    """Shell steps that put the pinned typst on PATH inside the image."""
    if tc.build_from_source:
        return [
            "cargo install --locked --git https://github.com/typst/typst"
            f" --tag v{tc.version} typst-cli",
            f"install -m 0755 /root/.cargo/bin/typst {BIN_DIR}/typst",
        ]
    url = release_url(tc.version, arch)
    digest = expected_sha256(tc, arch)
    return [
        f"curl -fsSL -o /tmp/typst.tar.xz {shlex.quote(url)}",
        f'echo "{digest}  /tmp/typst.tar.xz" | sha256sum -c -',
        f"tar -xJf /tmp/typst.tar.xz -C /tmp typst-{arch}-unknown-linux-musl/typst",
        f"install -m 0755 /tmp/typst-{arch}-unknown-linux-musl/typst {BIN_DIR}/typst",
        "rm -rf /tmp/typst.tar.xz /tmp/typst-*",
        "typst --version",
    ]


def predownload_commands(packages: list[str]) -> list[str]:
    """Steps that fetch each declared package into the image's cache.

    typst has no download command; importing a package from a stub document
    is what populates the cache, exactly as a build would.
    """
    if not packages:
        return []
    # A package spec is a string in Typst source; the stub is a single-quoted
    # shell word, so the double quotes travel as they are.
    for p in packages:
        parse_package(p)  # only well-formed specs reach the shell
    stub = "".join(f'#import "{p}"\\n' for p in packages)
    return [
        f"mkdir -p {PACKAGE_CACHE_PATH} {PACKAGE_PATH}",
        f"printf '{stub}' > /tmp/predownload.typ",
        f"TYPST_PACKAGE_CACHE_PATH={PACKAGE_CACHE_PATH}"
        " typst compile /tmp/predownload.typ /tmp/predownload.pdf",
        "rm -f /tmp/predownload.typ /tmp/predownload.pdf",
    ]


def parse_banner(line: str) -> str | None:
    """The version in a `typst --version` line, which heads a Typst build log."""
    m = _BANNER_RE.match(line.strip())
    return m["version"] if m else None


def toolchain_mismatch(tc: TypstConfig, version: str) -> str | None:
    """Why a PDF built with typst *version* cannot come from the configured one."""
    if version != tc.version:
        return f"built with typst {version}; config expects {tc.version}"
    return None
