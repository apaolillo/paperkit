# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""ACM profile, for the acmart class."""

from paperkit.profiles import BaseProfile, Defaults


class ACMProfile(BaseProfile):
    """Defaults for a paper in the acmart class, at an ACM venue."""

    def defaults(self) -> Defaults:
        d = super().defaults()
        # TAPS compiles the sources itself and does not run BibTeX, so the
        # archive carries the class files a project overrides and the .bbl.
        d["zip"]["include"] += ["acmart.cls", "ACM-Reference-Format.bst"]
        d["zip"]["include_bbl"] = True
        # A fourth pass lets pbalance balance the columns of the last page.
        d["build"] = {"passes": 4}
        # ACM calls state the limit for the body with acknowledgments inside
        # it and exempt only the references.
        d["page_limits"] = {"ack_counts_as_content": True}
        return d
