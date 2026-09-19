# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Tests for how the Docker image installs paperkit itself."""

import pytest
from pythainer.builders import render_dockerfile_content

from paperkit import __version__, docker
from paperkit.config import PaperkitConfig


def _dockerfile() -> str:
    builder = docker.make_builder(PaperkitConfig())
    return render_dockerfile_content(package_manager="apt", commands=builder._build_commands)


def test_source_checkout_copies_only_what_pip_needs() -> None:
    assert docker._is_source_checkout()
    dockerfile = _dockerfile()
    for name in docker._PAPERKIT_SRC_FILES:
        assert f"COPY {name} {docker.CONTAINER_PAPERKIT}/{name}" in dockerfile
    assert f"pip install --break-system-packages {docker.CONTAINER_PAPERKIT}" in dockerfile
    assert "COPY paperkit " not in dockerfile  # never the whole repository


def test_installed_package_installs_same_version_from_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(docker, "_is_source_checkout", lambda: False)
    dockerfile = _dockerfile()
    assert f"pip install --break-system-packages paperkit=={__version__}" in dockerfile
    assert "COPY" not in dockerfile.split("# Install paperkit CLI")[1]
