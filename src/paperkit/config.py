# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Load and validate .paperkit.toml configuration."""

import datetime as dt
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperkit import reproducible, typst
from paperkit.profiles import get_profile
from paperkit.typst import TypstConfig


@dataclass
class BibtexTidyConfig:
    enabled: bool = True
    version: str = "1.14.0"
    # Sort entries by key and fields within entries. False keeps the file's
    # own order, for both `paperkit bibtidy` and the tidiness check.
    sort: bool = True


@dataclass
class UnusedBibConfig:
    enabled: bool = True
    # Keys never reported as unused (e.g. an entry staged to be cited later).
    ignore: list[str] = field(default_factory=list)
    # When another target sharing a bib file has no up-to-date .aux, run one
    # draft LaTeX pass (no PDF) to learn its citations. When false, entries
    # its citations could cover are reported as "not checked", never unused.
    draft_pass: bool = True


@dataclass
class ChecksConfig:
    non_ascii: bool = True
    trailing_whitespace: bool = True
    final_newline: bool = True
    unused_bib: UnusedBibConfig = field(default_factory=UnusedBibConfig)
    font_embedding: bool = True
    # Part of the font_embedding check: warn on Type 3 (bitmap) fonts.
    no_type3: bool = True
    overfull_boxes: bool = True
    bibtex_tidy: BibtexTidyConfig = field(default_factory=BibtexTidyConfig)


@dataclass
class PageLimitsConfig:
    # Hard caps. None = no limit (informational only).
    total: int | None = None
    # Max pages the content before the section may occupy. A section starting
    # mid-page counts that page against the budget.
    before_refs: int | None = None
    before_ack: int | None = None
    # False (default): references and acknowledgments are both exempt, so the
    # budget ends at whichever comes first. True: only the references are
    # exempt, as at venues that count acknowledgments as text.
    ack_counts_as_content: bool = False
    # Regex patterns used to spot the section in the .aux TOC entries.
    refs_pattern: str = r"(?i)\b(references|bibliography)\b"
    ack_pattern: str = r"(?i)acknowledg"


@dataclass
class TexliveConfig:
    # "distro": the base image's texlive-* packages. "upstream": install-tl
    # from a tlnet repository (see paperkit.texlive for URL resolution).
    source: str = "distro"
    # Repository selection, highest precedence first: repository > snapshot
    # (YYYY-MM-DD, dated tlnet archive) > year (frozen tlnet-final of a
    # closed release) > live CTAN mirror (not reproducible).
    repository: str | None = None
    snapshot: str | None = None
    year: int | None = None
    # Expected sha512 of the repository's tlpkg/texlive.tlpdb, checked before
    # installing so a changed repository fails the image build.
    tlpdb_sha512: str | None = None
    scheme: str = "small"
    collections: list[str] = field(default_factory=list)
    # Individual packages installed with tlmgr after install-tl.
    packages: list[str] = field(default_factory=list)
    docs: bool = False
    sources: bool = False


@dataclass
class ZipConfig:
    name: str = ""
    include: list[str] = field(default_factory=list)
    # Add each included main's compiled bibliography (<main>.bbl, from the
    # build directory) next to its .tex. Publishers that compile without
    # running BibTeX need it; Springer's LNCS checklist asks for it.
    include_bbl: bool = False
    exclude: list[str] = field(
        default_factory=lambda: ["*.aux", "*.log", "*.out", "*.blg", "*.bbl"],
    )


@dataclass
class PaperkitConfig:
    # [project]
    # main is kept as a convenience for the single-target case and always
    # equals mains[0]. mains is the canonical list the build/check loops over.
    main: str = "main"
    mains: list[str] = field(default_factory=list)
    content_dirs: list[str] = field(default_factory=lambda: ["content"])
    bib: str = ""

    # [build]
    engine: str = "pdflatex"
    passes: int = 3
    shell_escape: bool = True
    bibtex: bool = True
    biber: bool = False
    output_dir: str = "out"
    # None = use cpu_count. A positive int caps parallel workers; useful when
    # one main includes the PDF output of another (`\includepdf`) and needs
    # to build after it.
    jobs: int | None = None
    # Timestamp every tool builds with, for byte-identical rebuilds: an
    # epoch, an ISO date, or "git" (HEAD's committer date).
    source_date_epoch: int | str = "git"

    # [docker]
    base_image: str = "ubuntu:26.04"
    image_name: str = "paperkit-builder"
    extra_packages: list[str] = field(default_factory=list)
    debconf_selections: list[str] = field(default_factory=list)

    # [texlive]
    texlive: TexliveConfig = field(default_factory=TexliveConfig)

    # [typst]
    typst: TypstConfig = field(default_factory=TypstConfig)

    # [checks]
    checks: ChecksConfig = field(default_factory=ChecksConfig)

    # [page_limits]
    page_limits: PageLimitsConfig = field(default_factory=PageLimitsConfig)

    # [zip]
    zip: ZipConfig = field(default_factory=ZipConfig)

    # [profile]
    profile_name: str = "acm"

    # resolved root directory (where .paperkit.toml lives)
    root: Path = field(default_factory=lambda: Path.cwd())

    @property
    def is_typst(self) -> bool:
        return self.engine == "typst"

    @property
    def main_suffix(self) -> str:
        """The source extension of a main: .typ for Typst, .tex otherwise."""
        return ".typ" if self.is_typst else ".tex"

    def main_file(self, main: str) -> Path:
        return self.root / f"{main}{self.main_suffix}"


ENGINES = ("pdflatex", "lualatex", "xelatex", "typst")

TEXLIVE_SCHEMES = (
    "basic",
    "context",
    "full",
    "gust",
    "infraonly",
    "medium",
    "minimal",
    "small",
    "tetex",
)

# Debian's texlive-* package names differ from TeX Live collection names.
_DEBIAN_COLLECTION_NAMES = {"science": "mathscience"}

# Names end up in a shell command and an install-tl profile, so keep them to
# the character set CTAN package names actually use.
_TL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SHA512_RE = re.compile(r"[0-9a-f]{128}")


def _strip_prefix(name: str, prefix: str) -> str:
    return name[len(prefix) :] if name.startswith(prefix) else name


def _str_list(section: str, key: str, value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"[{section}] {key}: expected a list of strings")
    return value


def parse_typst(raw: dict[str, object]) -> TypstConfig:
    """Build a TypstConfig from the [typst] table, rejecting bad values early."""
    tc = TypstConfig()
    known = set(TypstConfig.__dataclass_fields__)
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(
            f"[typst] unknown key(s): {', '.join(unknown)} (expected: {', '.join(sorted(known))})",
        )
    if "version" in raw:
        version = raw["version"]
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError(f'[typst] version: expected "X.Y.Z", got {version!r}')
        tc.version = version
    if "sha256" in raw:
        digest = raw["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("[typst] sha256: expected 64 hex characters")
        tc.sha256 = digest
    for key in ("build_from_source", "ignore_system_fonts"):
        if key in raw:
            if not isinstance(raw[key], bool):
                raise ValueError(f"[typst] {key}: expected true or false")
            setattr(tc, key, raw[key])
    for key in ("fonts", "packages", "extra_args"):
        if key in raw:
            setattr(tc, key, _str_list("typst", key, raw[key]))
    for spec in tc.packages:
        typst.parse_package(spec)
    for key in ("packages_dir", "pdf_standard"):
        if key in raw:
            if not isinstance(raw[key], str) or not raw[key]:
                raise ValueError(f"[typst] {key}: expected a non-empty string")
            setattr(tc, key, raw[key])
    return tc


def parse_texlive(raw: dict[str, object]) -> TexliveConfig:
    """Build a TexliveConfig from the [texlive] table, rejecting bad values early."""
    tl = TexliveConfig()
    known = set(TexliveConfig.__dataclass_fields__)
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(
            f"[texlive] unknown key(s): {', '.join(unknown)} "
            f"(expected: {', '.join(sorted(known))})",
        )

    source = raw.get("source", tl.source)
    if not isinstance(source, str) or source not in ("distro", "upstream"):
        raise ValueError(f'[texlive] source: expected "distro" or "upstream", got {source!r}')
    tl.source = source

    if "snapshot" in raw and "year" in raw:
        raise ValueError("[texlive] snapshot and year are mutually exclusive; set only one")

    if "snapshot" in raw:
        snapshot = raw["snapshot"]
        # A bare TOML date (snapshot = 2026-09-18) parses as datetime.date.
        if isinstance(snapshot, dt.date) and not isinstance(snapshot, dt.datetime):
            snapshot = snapshot.isoformat()
        if not isinstance(snapshot, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", snapshot):
            raise ValueError(f'[texlive] snapshot: expected "YYYY-MM-DD", got {snapshot!r}')
        try:
            dt.date.fromisoformat(snapshot)
        except ValueError:
            raise ValueError(f"[texlive] snapshot: not a valid date: {snapshot!r}") from None
        tl.snapshot = snapshot

    if "year" in raw:
        year = raw["year"]
        if not isinstance(year, int) or isinstance(year, bool) or year < 2008:
            raise ValueError(
                f"[texlive] year: expected a TeX Live release year >= 2008, got {year!r}",
            )
        tl.year = year

    if "repository" in raw:
        repo = raw["repository"]
        if not isinstance(repo, str) or not re.fullmatch(r"(https?|ftp)://\S+", repo):
            raise ValueError(
                f"[texlive] repository: expected an http(s):// or ftp:// URL, got {repo!r}",
            )
        tl.repository = repo.rstrip("/")

    if "tlpdb_sha512" in raw:
        digest = raw["tlpdb_sha512"]
        if not isinstance(digest, str) or not _SHA512_RE.fullmatch(digest.lower()):
            raise ValueError("[texlive] tlpdb_sha512: expected 128 hex characters")
        tl.tlpdb_sha512 = digest.lower()

    if "scheme" in raw:
        scheme = raw["scheme"]
        name = _strip_prefix(scheme, "scheme-") if isinstance(scheme, str) else ""
        if name not in TEXLIVE_SCHEMES:
            raise ValueError(
                f"[texlive] scheme: unknown scheme {scheme!r} "
                f"(expected one of: {', '.join(TEXLIVE_SCHEMES)})",
            )
        tl.scheme = name

    for key in ("collections", "packages"):
        if key not in raw:
            continue
        names = _str_list("texlive", key, raw[key])
        if key == "collections":
            names = [_strip_prefix(n, "collection-") for n in names]
            for n in names:
                hint = _DEBIAN_COLLECTION_NAMES.get(n) or (n.replace("-", "") if "-" in n else None)
                if hint:
                    raise ValueError(
                        f"[texlive] collections: {n!r} looks like a Debian package name; "
                        f"the TeX Live collection is {hint!r}",
                    )
        bad = [n for n in names if not _TL_NAME_RE.fullmatch(n)]
        if bad:
            raise ValueError(f"[texlive] {key}: invalid name(s): {', '.join(map(repr, bad))}")
        setattr(tl, key, names)

    for key in ("docs", "sources"):
        if key in raw:
            if not isinstance(raw[key], bool):
                raise ValueError(f"[texlive] {key}: expected true or false")
            setattr(tl, key, raw[key])

    return tl


def parse_unused_bib(raw: object) -> UnusedBibConfig:
    """`unused_bib = true|false`, or a `[checks.unused_bib]` table."""
    ub = UnusedBibConfig()
    if isinstance(raw, bool):
        ub.enabled = raw
        return ub
    if not isinstance(raw, dict):
        raise ValueError("[checks] unused_bib: expected true, false or a table")
    unknown = sorted(set(raw) - set(UnusedBibConfig.__dataclass_fields__))
    if unknown:
        raise ValueError(f"[checks.unused_bib] unknown key(s): {', '.join(unknown)}")
    for key in ("enabled", "draft_pass"):
        if key in raw:
            if not isinstance(raw[key], bool):
                raise ValueError(f"[checks.unused_bib] {key}: expected true or false")
            setattr(ub, key, raw[key])
    if "ignore" in raw:
        ub.ignore = _str_list("checks.unused_bib", "ignore", raw["ignore"])
    return ub


def find_config(start: Path | None = None) -> Path:
    """Walk up from *start* to find .paperkit.toml."""
    d = (start or Path.cwd()).resolve()
    while True:
        candidate = d / ".paperkit.toml"
        if candidate.is_file():
            return candidate
        parent = d.parent
        if parent == d:
            raise FileNotFoundError("No .paperkit.toml found in any parent directory")
        d = parent


def _with_profile_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    """Lay the profile's defaults under the file's own tables.

    Resolved before anything else is parsed, so a default reads exactly as
    if it had been written in .paperkit.toml, and the file's own keys win.
    """
    profile = raw.get("profile", {})
    name = profile.get("name", PaperkitConfig.profile_name) if isinstance(profile, dict) else None
    if not isinstance(name, str):
        raise ValueError("[profile] name: expected a string")
    merged = dict(raw)
    for section, keys in get_profile(name).defaults().items():
        table = dict(merged.get(section, {}))
        for key, value in keys.items():
            table.setdefault(key, value)
        merged[section] = table
    return merged


def load_config(path: Path | None = None) -> PaperkitConfig:
    """Load .paperkit.toml and return a PaperkitConfig."""
    if path is None:
        path = find_config()
    raw = _with_profile_defaults(tomllib.loads(path.read_text()))

    cfg = PaperkitConfig(root=path.parent.resolve())

    # [project]
    proj = raw.get("project", {})
    if "content_dirs" in proj:
        cfg.content_dirs = proj["content_dirs"]
    if "bib" in proj:
        cfg.bib = proj["bib"]

    # main / mains: accept either key, each may be a string or a list of strings,
    # and entries may be globs that match against <root>/<pattern>.tex.
    raw_patterns: list[str] = []
    for key in ("main", "mains"):
        if key not in proj:
            continue
        v = proj[key]
        if isinstance(v, str):
            raw_patterns.append(v)
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            raw_patterns.extend(v)
        else:
            raise ValueError(f"[project] {key}: expected string or list of strings")

    if not raw_patterns:
        raw_patterns = ["main"]

    # The engine decides what a main is called, so it is read before the
    # names are expanded; the rest of [build] follows below.
    build = raw.get("build", {})
    if "engine" in build:
        cfg.engine = build["engine"]
    if cfg.engine not in ENGINES:
        raise ValueError(
            f"[build] engine: expected one of {', '.join(ENGINES)}, got {cfg.engine!r}"
        )
    suffix = cfg.main_suffix

    expanded: list[str] = []
    seen: set[str] = set()
    for pat in raw_patterns:
        if any(c in pat for c in "*?["):
            matches = sorted(p.stem for p in cfg.root.glob(f"{pat}{suffix}"))
            if not matches:
                raise FileNotFoundError(
                    f"[project] '{pat}' matched no {suffix} files in {cfg.root}",
                )
            for m in matches:
                if m not in seen:
                    expanded.append(m)
                    seen.add(m)
        elif pat not in seen:
            expanded.append(pat)
            seen.add(pat)

    cfg.mains = expanded
    cfg.main = expanded[0]

    # [build]
    for key in ("passes", "shell_escape", "bibtex", "biber", "output_dir", "jobs"):
        if key in build:
            setattr(cfg, key, build[key])
    if "source_date_epoch" in build:
        cfg.source_date_epoch = reproducible.parse_setting(build["source_date_epoch"])

    # [docker]
    docker = raw.get("docker", {})
    for key in ("base_image", "image_name", "extra_packages", "debconf_selections"):
        if key in docker:
            setattr(cfg, key, docker[key])

    # [texlive]
    cfg.texlive = parse_texlive(raw.get("texlive", {}))

    # [typst]
    cfg.typst = parse_typst(raw.get("typst", {}))

    # [checks]
    checks_raw = raw.get("checks", {})
    checks = ChecksConfig()
    check_keys = (
        "non_ascii",
        "trailing_whitespace",
        "final_newline",
        "font_embedding",
        "no_type3",
        "overfull_boxes",
    )
    for key in check_keys:
        if key in checks_raw:
            setattr(checks, key, checks_raw[key])
    checks.unused_bib = parse_unused_bib(checks_raw.get("unused_bib", True))
    bt = checks_raw.get("bibtex_tidy", {})
    if isinstance(bt, dict):
        if "enabled" in bt:
            checks.bibtex_tidy.enabled = bt["enabled"]
        if "version" in bt:
            checks.bibtex_tidy.version = bt["version"]
        if "sort" in bt:
            if not isinstance(bt["sort"], bool):
                raise ValueError("[checks] bibtex_tidy.sort: expected true or false")
            checks.bibtex_tidy.sort = bt["sort"]
    cfg.checks = checks

    # [page_limits]
    pl_raw = raw.get("page_limits", {})
    pl = PageLimitsConfig()
    for key in ("total", "before_refs", "before_ack", "refs_pattern", "ack_pattern"):
        if key in pl_raw:
            setattr(pl, key, pl_raw[key])
    if "ack_counts_as_content" in pl_raw:
        value = pl_raw["ack_counts_as_content"]
        if not isinstance(value, bool):
            raise ValueError("[page_limits] ack_counts_as_content: expected true or false")
        pl.ack_counts_as_content = value
    cfg.page_limits = pl

    # [zip]
    zip_raw = raw.get("zip", {})
    z = ZipConfig()
    if "name" in zip_raw:
        z.name = zip_raw["name"]
    else:
        z.name = cfg.main
    if "include" in zip_raw:
        z.include = zip_raw["include"]
    if "exclude" in zip_raw:
        z.exclude = zip_raw["exclude"]
    if "include_bbl" in zip_raw:
        if not isinstance(zip_raw["include_bbl"], bool):
            raise ValueError("[zip] include_bbl: expected true or false")
        z.include_bbl = zip_raw["include_bbl"]
    cfg.zip = z

    # [profile]
    profile = raw.get("profile", {})
    if "name" in profile:
        cfg.profile_name = profile["name"]

    return cfg
