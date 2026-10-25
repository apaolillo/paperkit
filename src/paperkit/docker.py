# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Docker image building and container execution via pythainer."""

import contextlib
import io
import os
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path

from pythainer.builders import UbuntuDockerBuilder
from pythainer.runners import ConcreteDockerRunner

from paperkit import __version__, texlive, typst
from paperkit.config import PaperkitConfig
from paperkit.profiles import BaseProfile

# Lines of captured build output shown when a quiet image build fails.
_FAILURE_TAIL_LINES = 30
_FAILURE_LINE_WIDTH = 200

CONTAINER_WORKDIR = Path("/paper")
CONTAINER_PAPERKIT = Path("/opt/paperkit")

# Distro TeX packages (for [texlive] source = "distro"), always installed
# together so that switching engine (pdflatex <-> lualatex) or bibliography
# backend (bibtex <-> biber) does not require a Docker image rebuild.
_DISTRO_TEX_PACKAGES = [
    # TeX Live - all engines and common collections
    "texlive-latex-recommended",
    "texlive-latex-extra",
    "texlive-luatex",
    "texlive-xetex",
    "texlive-fonts-recommended",
    "texlive-fonts-extra",
    "texlive-bibtex-extra",
    "texlive-science",
    "texlive-pictures",
    "texlive-publishers",
    "texlive-plain-generic",
    "texlive-extra-utils",
    # Bibliography
    "biber",
    # minted's highlighter
    "python3-pygments",
]

# Tools paperkit itself needs, whatever the TeX Live source.
_TOOL_PACKAGES = [
    "python3-pip",
    "poppler-utils",
    "npm",
    "unzip",
    "pandoc",  # used by text_export to strip LaTeX from \title and \begin{abstract}
]

# paperkit source root: two levels up from this file (src/paperkit/ -> src/ -> repo root)
_PAPERKIT_SRC_ROOT = Path(__file__).resolve().parent.parent.parent
# What `pip install` needs from a source checkout (README and LICENSE are
# referenced by pyproject.toml). Copying only these keeps .git, .venv and
# working files out of the image and its layer cache.
_PAPERKIT_SRC_FILES = ("pyproject.toml", "README.md", "LICENSE", "src")


def _is_source_checkout() -> bool:
    """True when paperkit runs from a source tree rather than an installed wheel."""
    return all((_PAPERKIT_SRC_ROOT / name).exists() for name in _PAPERKIT_SRC_FILES)


@contextlib.contextmanager
def _quiet_stdout_stderr(verbose: bool) -> Generator[None]:
    """Suppress both stdout and stderr unless verbose.

    pythainer prints [SHELL] lines to stdout; Docker BuildKit progress goes
    to stderr via inherited file descriptors in subprocess.check_call.
    """
    if verbose:
        yield
        return

    # Capture Python-level stdout (pythainer's print() calls)
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    # Redirect OS-level stderr fd (Docker BuildKit output) to a temp file, so
    # the tail can be shown if the build fails.
    saved_stderr_fd = os.dup(2)
    with tempfile.TemporaryFile() as captured:
        os.dup2(captured.fileno(), 2)
        try:
            yield
        except BaseException:
            os.dup2(saved_stderr_fd, 2)
            captured.seek(0)
            tail = captured.read().decode(errors="replace").splitlines()[-_FAILURE_TAIL_LINES:]
            # BuildKit echoes whole RUN commands; cut those so the error stays readable.
            print("\n".join(line[:_FAILURE_LINE_WIDTH] for line in tail), file=sys.stderr)
            raise
        finally:
            sys.stdout = old_stdout
            os.dup2(saved_stderr_fd, 2)
            os.close(saved_stderr_fd)


@contextlib.contextmanager
def _quiet_stdout(verbose: bool) -> Generator[None]:
    """Suppress only stdout (pythainer's [SHELL] lines) unless verbose."""
    if verbose:
        yield
        return

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout


def build_image(config: PaperkitConfig, verbose: bool = False) -> str:
    """Build the Docker image and return its tag."""
    tl = config.texlive
    if tl.source == "upstream" and not texlive.is_pinned(tl):
        print(
            'warning: [texlive] source = "upstream" without snapshot, year or repository '
            f"installs from the live CTAN repository ({texlive.LIVE_REPOSITORY}); "
            'rebuilds will pick up newer packages. Set snapshot = "YYYY-MM-DD" to pin it.',
            file=sys.stderr,
        )

    builder = make_builder(config)

    # Suppress both stdout ([SHELL] lines) and stderr (BuildKit progress)
    try:
        with _quiet_stdout_stderr(verbose):
            builder.build()
    except subprocess.CalledProcessError:
        print(
            f"Docker image build failed ({config.image_name}); see output above.",
            file=sys.stderr,
        )
        sys.exit(1)
    return config.image_name


# Everything paperkit needs beside the compiler; pandoc is for the LaTeX text export.
_TYPST_TOOL_PACKAGES = [p for p in _TOOL_PACKAGES if p != "pandoc"]
_TYPST_PREREQS = ["ca-certificates", "curl", "xz-utils", "fontconfig"]
_RUST_PREREQS = ["build-essential", "pkg-config", "libssl-dev", "git"]
_IMAGE_FONT_DIRS = ["/usr/share/fonts", "/usr/share/texmf/fonts"]


def _typst_layers(
    builder: UbuntuDockerBuilder, config: PaperkitConfig, profile: BaseProfile
) -> None:
    """The image of a Typst project: no TeX Live, a pinned typst, its packages.

    Layers go from the most stable to the most project-specific, so a change
    to the declared packages does not reinstall the compiler.
    """
    tc = config.typst
    builder.desc("Install tools and profile packages")
    builder.add_packages(_TYPST_PREREQS + _TYPST_TOOL_PACKAGES + profile.docker_packages())
    builder.space()

    if tc.build_from_source:
        builder.desc("Install a Rust toolchain to build typst from source")
        builder.add_packages(_RUST_PREREQS)
        builder.run("curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal")
        builder.env("PATH", "/root/.cargo/bin:${PATH}")
        builder.space()

    builder.desc(f"Install typst {tc.version}" + (" from source" if tc.build_from_source else ""))
    builder.run_multiple(typst.install_commands(tc, typst.host_arch()))
    # Fonts installed into the image (profile and extra packages) are part of
    # the pinned environment, unlike a host's: make them visible to a build
    # that otherwise ignores system fonts. Debian puts font packages under
    # /usr/share/fonts, and the TeX ones (TeX Gyre among them) under texmf.
    builder.run(f"mkdir -p {' '.join(_IMAGE_FONT_DIRS)}")
    builder.env("TYPST_FONT_PATHS", ":".join(_IMAGE_FONT_DIRS))
    builder.space()

    # Declared packages are fetched into the image's cache; the container's
    # user must be able to write there too, for an import nobody declared.
    builder.desc("Typst package directories")
    builder.env("TYPST_PACKAGE_PATH", typst.PACKAGE_PATH)
    builder.env("TYPST_PACKAGE_CACHE_PATH", typst.PACKAGE_CACHE_PATH)
    builder.run(f"mkdir -p {typst.PACKAGE_PATH} {typst.PACKAGE_CACHE_PATH}")
    if tc.packages:
        builder.run_multiple(typst.predownload_commands(tc.packages))
    builder.run(f"chmod -R a+rwX {typst.PACKAGE_CACHE_PATH} && chmod -R a+rX {typst.PACKAGE_PATH}")
    builder.space()


def make_builder(config: PaperkitConfig) -> UbuntuDockerBuilder:
    """Assemble the image definition (Dockerfile + build context) for *config*."""
    from paperkit.profiles import get_profile

    profile = get_profile(config.profile_name)
    tl = config.texlive

    builder = UbuntuDockerBuilder(
        tag=config.image_name,
        ubuntu_base_tag=config.base_image,
    )
    builder.space()

    # Run apt-get / dpkg without interactive prompts. Without this, packages
    # whose postinst scripts call debconf (e.g. ttf-mscorefonts-installer)
    # try the Dialog/Readline/Teletype frontends and fail in BuildKit because
    # there's no TTY.
    builder.env("DEBIAN_FRONTEND", "noninteractive")
    builder.space()

    if config.is_typst:
        _typst_layers(builder, config, profile)
    elif tl.source == "upstream":
        # Prerequisites and TeX Live get their own layers ahead of the tools,
        # so the (large) TeX Live layer only rebuilds when [texlive] changes.
        builder.desc("Install prerequisites for upstream TeX Live")
        builder.add_packages(texlive.APT_PREREQS)
        builder.space()

        builder.desc(f"Install TeX Live ({texlive.describe(tl)})")
        builder.run_multiple(texlive.install_commands(tl))
        builder.env("PATH", f"{texlive.BIN_DIR}:${{PATH}}")
        builder.space()

        builder.desc("Install tools and profile packages")
        builder.add_packages(_TOOL_PACKAGES + profile.docker_packages())
        builder.space()
    else:
        # Base + profile packages in one layer so the cache is shared across
        # all paperkit projects regardless of their per-project extra_packages.
        builder.desc("Install TeX Live and dependencies")
        builder.add_packages(_DISTRO_TEX_PACKAGES + _TOOL_PACKAGES + profile.docker_packages())
        builder.space()

    # Pre-seed debconf answers (e.g. EULA acceptance) before installing
    # project extras. Must run before add_packages so the postinst scripts
    # see the preseeded values.
    if config.debconf_selections:
        builder.desc("Pre-seed debconf selections")
        joined = " && ".join(
            f"echo {shlex.quote(s)} | debconf-set-selections" for s in config.debconf_selections
        )
        builder.run(joined)
        builder.space()

    # Project-specific extras in a separate layer: only this layer is rebuilt
    # when extra_packages changes between projects.
    if config.extra_packages:
        builder.desc("Install project-specific extra packages")
        builder.add_packages(config.extra_packages)
        builder.space()

    # bibtex-tidy
    if config.checks.bibtex_tidy.enabled:
        version = config.checks.bibtex_tidy.version
        builder.desc("Install bibtex-tidy for bib file linting")
        builder.run(f"npm install -g bibtex-tidy@{version}")
        builder.space()

    # Copy and install paperkit into the image
    builder.desc("Install paperkit CLI")
    if _is_source_checkout():
        for name in _PAPERKIT_SRC_FILES:
            builder.copy(source=_PAPERKIT_SRC_ROOT / name, destination=CONTAINER_PAPERKIT / name)
        builder.run(f"pip install --break-system-packages {CONTAINER_PAPERKIT}")
    else:
        # Installed from a package index: install the same version in the image.
        builder.run(f"pip install --break-system-packages paperkit=={__version__}")
    builder.space()

    builder.desc("Set working directory")
    builder.workdir(CONTAINER_WORKDIR)
    return builder


def container_volumes(config: PaperkitConfig) -> dict[str, str]:
    """The project at the working directory, plus a Typst project's local packages.

    The local packages tree is mounted read-only where typst looks for
    package namespaces, so a template kept outside Universe resolves without
    being copied into the image.
    """
    volumes = {str(config.root): str(CONTAINER_WORKDIR)}
    if config.is_typst and config.typst.packages_dir:
        host = Path(config.typst.packages_dir).expanduser().resolve()
        if host.is_dir():
            volumes[str(host)] = f"{typst.PACKAGE_PATH}:ro"
        else:
            print(f"  warning: [typst] packages_dir {host} is not a directory; not mounted")
    return volumes


def run_in_docker(
    config: PaperkitConfig,
    command: str,
    interactive: bool = False,
    verbose: bool = False,
    env: dict[str, str] | None = None,
) -> int:
    """Run a command inside the Docker container. Returns exit code.

    *env* is passed with `docker run --env`. The build timestamp travels this
    way: the image has no git, so the host resolves it and the inner paperkit
    picks it up from the environment.
    """
    runner = ConcreteDockerRunner(
        image=config.image_name,
        name=f"{config.image_name}-run",
        volumes=container_volumes(config),
        environment_variables=env or {},
        workdir=CONTAINER_WORKDIR,
        tty=True,
        interactive=interactive,
    )

    # Only suppress stdout ([SHELL] lines); keep stderr so the container's
    # actual output (build progress, checks) is visible to the user.
    try:
        with _quiet_stdout(verbose):
            runner.run(commands=[command])
    except subprocess.CalledProcessError as e:
        return e.returncode
    return 0
