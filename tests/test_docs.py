# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""The configuration reference must keep up with the dataclasses.

A new key is easy to add and easy to forget to document; these tests fail
when the two drift apart. The docs are not part of the sdist, so they skip
when only the package and its tests are present.
"""

from dataclasses import fields
from pathlib import Path

import pytest

from paperkit.config import (
    BibtexTidyConfig,
    ChecksConfig,
    PageLimitsConfig,
    PaperkitConfig,
    TexliveConfig,
    UnusedBibConfig,
    ZipConfig,
)

DOC = Path(__file__).resolve().parents[1] / "docs" / "configuration.md"

pytestmark = pytest.mark.skipif(not DOC.is_file(), reason="docs/ is not in the sdist")

# root is the resolved project directory, not a config key; profile_name is
# documented as `name` under [profile]; and the fields holding a nested table
# are covered by the section test below rather than as keys of their own.
NOT_KEYS = {"root", "profile_name", "texlive", "checks", "page_limits", "zip"}

CONFIGS = (
    PaperkitConfig,
    TexliveConfig,
    ChecksConfig,
    UnusedBibConfig,
    BibtexTidyConfig,
    PageLimitsConfig,
    ZipConfig,
)


def _documented() -> str:
    return DOC.read_text()


@pytest.mark.parametrize("config", CONFIGS, ids=lambda c: c.__name__)
def test_every_config_key_is_documented(config: type) -> None:
    text = _documented()
    missing = [
        f.name for f in fields(config) if f.name not in NOT_KEYS and f"`{f.name}`" not in text
    ]
    assert not missing, f"undocumented in docs/configuration.md: {', '.join(missing)}"


def test_every_section_is_documented() -> None:
    text = _documented()
    sections = ["project", "build", "docker", "texlive", "checks", "page_limits", "zip", "profile"]
    missing = [s for s in sections if f"## [{s}]" not in text]
    assert not missing, f"sections missing from docs/configuration.md: {', '.join(missing)}"
