# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Profiles for Typst papers at the venues the LaTeX profiles cover.

The venue rules are the same as for the LaTeX siblings; what differs is the
archive. A Typst build carries its bibliography in the PDF, so there is no
.bbl to ship, and the sources are .typ files plus whatever the project
imports: bibliographies, fonts, and any local template the compilation read,
which `paperkit zip` takes from the build's dependency list on top of these
patterns.
"""

from paperkit.profiles import BaseProfile, Defaults

_TYPST_SOURCES = ["{main}.typ", "**/*.typ", "**/*.bib", "**/*.yml", "**/*.yaml", "fonts/**"]


class TypstBaseProfile(BaseProfile):
    """Typst sources and bibliographies in the archive, nothing venue-specific."""

    def defaults(self) -> Defaults:
        return {"zip": {"include": list(_TYPST_SOURCES), "include_bbl": False}}


class TypstIEEEProfile(TypstBaseProfile):
    """A Typst paper in an IEEE template, such as Universe's charged-ieee."""

    def docker_packages(self) -> list[str]:
        # charged-ieee sets TeX Gyre Termes and Cursor, the Times and Courier
        # clones IEEEtran uses too; Ubuntu packages them.
        return ["fonts-texgyre"]


class TypstACMProfile(TypstBaseProfile):
    """A Typst paper in an ACM template, such as Universe's faithful-acmart."""

    def defaults(self) -> Defaults:
        d = super().defaults()
        # The same rule as for acmart: the limit is stated for the body with
        # the acknowledgments inside it, and only the references are exempt.
        d["page_limits"] = {"ack_counts_as_content": True}
        return d
