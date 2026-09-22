# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Profile registry and base class."""

from paperkit.config import PaperkitConfig


class BaseProfile:
    """Base profile with sensible defaults."""

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


def get_profile(config: PaperkitConfig) -> BaseProfile:
    cls = _PROFILES.get(config.profile_name, BaseProfile)
    return cls()


# Register built-in profiles
register_profile("base", BaseProfile)

from paperkit.profiles.acm import ACMProfile  # noqa: E402

register_profile("acm", ACMProfile)
