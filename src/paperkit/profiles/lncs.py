# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""LNCS profile, for Springer's llncs class."""

from paperkit.profiles import BaseProfile, Defaults


class LNCSProfile(BaseProfile):
    """Defaults for a paper in the llncs class, in a Springer LNCS volume."""

    def defaults(self) -> Defaults:
        d = super().defaults()
        # Springer's camera-ready checklist asks for the sources the PDF was
        # built from and the compiled .bbl, since their pipeline does not run
        # BibTeX; a project carrying its own llncs.cls or splncs04.bst ships
        # them with the rest.
        d["zip"]["include"] += ["llncs.cls", "splncs04.bst"]
        d["zip"]["include_bbl"] = True
        return d
