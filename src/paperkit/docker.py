"""Docker image building and container execution via pythainer."""

import contextlib
import io
import os
import sys
from collections.abc import Generator
from pathlib import Path

from pythainer.builders import UbuntuDockerBuilder
from pythainer.runners import ConcreteDockerRunner

from paperkit.config import PaperkitConfig

CONTAINER_WORKDIR = Path("/paper")
CONTAINER_PAPERKIT = Path("/opt/paperkit")

# Packages always installed regardless of profile or config, so that switching
# engine (pdflatex ↔ lualatex) or bibliography backend (bibtex ↔ biber) does
# not require a Docker image rebuild.
_BASE_PACKAGES = [
    # TeX Live — all engines and common collections
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
    # Bibliography
    "biber",
    # Tools
    "python3-pygments",
    "python3-pip",
    "poppler-utils",
    "npm",
    "unzip",
]

# paperkit source root: two levels up from this file (src/paperkit/ -> src/ -> repo root)
_PAPERKIT_SRC_ROOT = Path(__file__).resolve().parent.parent.parent


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

    # Redirect OS-level stderr fd (Docker BuildKit output)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stderr_fd = os.dup(2)
    os.dup2(devnull_fd, 2)

    try:
        yield
    finally:
        sys.stdout = old_stdout
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stderr_fd)
        os.close(devnull_fd)


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
    from paperkit.profiles import get_profile

    profile = get_profile(config)

    builder = UbuntuDockerBuilder(
        tag=config.image_name,
        ubuntu_base_tag=config.base_image,
    )
    builder.space()

    # Base + profile packages in one layer so the cache is shared across all
    # paperkit projects regardless of their per-project extra_packages.
    builder.desc("Install TeX Live and dependencies")
    builder.add_packages(_BASE_PACKAGES + profile.docker_packages())
    builder.space()

    # Project-specific extras in a separate layer — only this layer is rebuilt
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
    builder.copy(source=_PAPERKIT_SRC_ROOT, destination=CONTAINER_PAPERKIT)
    builder.run(f"pip install --break-system-packages {CONTAINER_PAPERKIT}")
    builder.space()

    builder.desc("Set working directory")
    builder.workdir(CONTAINER_WORKDIR)

    # Suppress both stdout ([SHELL] lines) and stderr (BuildKit progress)
    with _quiet_stdout_stderr(verbose):
        builder.build()
    return config.image_name


def run_in_docker(
    config: PaperkitConfig,
    command: str,
    interactive: bool = False,
    verbose: bool = False,
) -> int:
    """Run a command inside the Docker container. Returns exit code."""
    runner = ConcreteDockerRunner(
        image=config.image_name,
        name=f"{config.image_name}-run",
        volumes={
            str(config.root): str(CONTAINER_WORKDIR),
        },
        workdir=CONTAINER_WORKDIR,
        tty=True,
        interactive=interactive,
    )

    # Only suppress stdout ([SHELL] lines); keep stderr so the container's
    # actual output (build progress, checks) is visible to the user.
    with _quiet_stdout(verbose):
        runner.run(commands=[command])
    return 0
