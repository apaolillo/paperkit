# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""USENIX profile, for the usenix style (OSDI, NSDI, ATC, Security, ...)."""

from paperkit.profiles import BaseProfile, Defaults


class USENIXProfile(BaseProfile):
    """Defaults for a paper in USENIX's template."""

    def defaults(self) -> Defaults:
        d = super().defaults()
        # USENIX calls state the limit as "N pages, not including references",
        # so the acknowledgments sit inside the budget. The style file itself
        # comes with the template, not with TeX Live, and the base list ships
        # it along with any other *.sty the project carries. Submission is a
        # PDF, so no archive conventions beyond that.
        d["page_limits"] = {"ack_counts_as_content": True}
        return d
