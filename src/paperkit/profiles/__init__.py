# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Profile registry and base class.

A profile carries what a venue's document class implies for a project: the
files worth shipping in the submission archive, whether the publisher wants
the compiled bibliography, how a page budget is counted. It contributes them
as configuration defaults, applied underneath .paperkit.toml, so anything
the project sets itself wins.
"""

from typing import Any

Defaults = dict[str, dict[str, Any]]


class BaseProfile:
    """Base profile with sensible defaults."""

    def defaults(self) -> Defaults:
        """Configuration defaults, in the shape of the TOML file.

        Keys the project sets replace these wholesale; a list is not merged.
        """
        return {
            "zip": {
                "include": ["{main}.tex", "content/**/*.tex", "**/*.bib", "*.sty"],
            },
        }

    def docker_packages(self) -> list[str]:
        """Extra packages beyond the base set (see docker._BASE_PACKAGES)."""
        return []

    # Reordering arguments, dropped when sorting is off.
    SORT_ARGS = ("--sort=key", "--sort-fields")

    def bibtex_tidy_args(self, sort: bool = True) -> list[str]:
        """Arguments for bibtex-tidy; *sort* also reorders entries and fields."""
        args = [
            "--curly",
            "--blank-lines",
            "--sort=key",
            "--duplicates=key,doi,citation",
            "--no-escape",
            "--sort-fields",
            "--trailing-commas",
            "--remove-empty-fields",
            "--enclosing-braces=title",
            "--align=13",
        ]
        return args if sort else [a for a in args if a not in self.SORT_ARGS]

    def bibtex_tidy_version(self) -> str:
        return "1.14.0"


_PROFILES: dict[str, type[BaseProfile]] = {}


def register_profile(name: str, cls: type[BaseProfile]) -> None:
    _PROFILES[name] = cls


def profile_names() -> list[str]:
    return sorted(_PROFILES)


def get_profile(name: str) -> BaseProfile:
    """The profile `[profile] name` selects; a name nobody registered is an error.

    Falling back to the base profile here would turn a typo into a silently
    different build.
    """
    try:
        cls = _PROFILES[name]
    except KeyError:
        known = ", ".join(profile_names())
        raise ValueError(
            f"[profile] name: unknown profile {name!r} (expected one of: {known})",
        ) from None
    return cls()


# Register built-in profiles
register_profile("base", BaseProfile)

from paperkit.profiles.acm import ACMProfile  # noqa: E402
from paperkit.profiles.ieee import IEEEProfile  # noqa: E402
from paperkit.profiles.lncs import LNCSProfile  # noqa: E402

register_profile("acm", ACMProfile)
register_profile("ieee", IEEEProfile)
register_profile("lncs", LNCSProfile)
