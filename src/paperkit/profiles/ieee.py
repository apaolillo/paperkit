# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""IEEE profile, for the IEEEtran class."""

from paperkit.profiles import BaseProfile, Defaults


class IEEEProfile(BaseProfile):
    """Defaults for a paper in the IEEEtran class, at an IEEE venue."""

    def defaults(self) -> Defaults:
        d = super().defaults()
        # PDF eXpress compiles submitted sources without running BibTeX and
        # asks for the .bbl; a project that pins its own IEEEtran.cls or .bst
        # ships them too.
        d["zip"]["include"] += ["IEEEtran.cls", "IEEEtran.bst"]
        d["zip"]["include_bbl"] = True
        return d
