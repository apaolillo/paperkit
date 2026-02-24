"""ACM sigconf profile — bibtex-tidy preferences for ACM papers."""

from typing import override

from paperkit.profiles import BaseProfile


class ACMProfile(BaseProfile):
    """Profile for ACM sigconf papers (acmart class)."""

    @override
    def bibtex_tidy_args(self) -> list[str]:
        return [
            *super().bibtex_tidy_args(),
            "--align=13",
            "--enclosing-braces=title",
        ]
