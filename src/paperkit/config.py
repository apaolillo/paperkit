"""Load and validate .paperkit.toml configuration."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BibtexTidyConfig:
    enabled: bool = True
    version: str = "1.14.0"


@dataclass
class ChecksConfig:
    non_ascii: bool = True
    trailing_whitespace: bool = True
    final_newline: bool = True
    unused_bib: bool = True
    font_embedding: bool = True
    overfull_boxes: bool = True
    bibtex_tidy: BibtexTidyConfig = field(default_factory=BibtexTidyConfig)


@dataclass
class ZipConfig:
    name: str = ""
    include: list[str] = field(default_factory=list)
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

    # [docker]
    base_image: str = "ubuntu:25.04"
    image_name: str = "paperkit-builder"
    extra_packages: list[str] = field(default_factory=list)
    debconf_selections: list[str] = field(default_factory=list)

    # [checks]
    checks: ChecksConfig = field(default_factory=ChecksConfig)

    # [zip]
    zip: ZipConfig = field(default_factory=ZipConfig)

    # [profile]
    profile_name: str = "acm"

    # resolved root directory (where .paperkit.toml lives)
    root: Path = field(default_factory=lambda: Path.cwd())


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


def load_config(path: Path | None = None) -> PaperkitConfig:
    """Load .paperkit.toml and return a PaperkitConfig."""
    if path is None:
        path = find_config()
    raw = tomllib.loads(path.read_text())

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

    expanded: list[str] = []
    seen: set[str] = set()
    for pat in raw_patterns:
        if any(c in pat for c in "*?["):
            matches = sorted(p.stem for p in cfg.root.glob(f"{pat}.tex"))
            if not matches:
                raise FileNotFoundError(
                    f"[project] '{pat}' matched no .tex files in {cfg.root}",
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
    build = raw.get("build", {})
    for key in ("engine", "passes", "shell_escape", "bibtex", "biber", "output_dir"):
        if key in build:
            setattr(cfg, key, build[key])

    # [docker]
    docker = raw.get("docker", {})
    for key in ("base_image", "image_name", "extra_packages", "debconf_selections"):
        if key in docker:
            setattr(cfg, key, docker[key])

    # [checks]
    checks_raw = raw.get("checks", {})
    checks = ChecksConfig()
    check_keys = (
        "non_ascii",
        "trailing_whitespace",
        "final_newline",
        "unused_bib",
        "font_embedding",
        "overfull_boxes",
    )
    for key in check_keys:
        if key in checks_raw:
            setattr(checks, key, checks_raw[key])
    bt = checks_raw.get("bibtex_tidy", {})
    if isinstance(bt, dict):
        if "enabled" in bt:
            checks.bibtex_tidy.enabled = bt["enabled"]
        if "version" in bt:
            checks.bibtex_tidy.version = bt["version"]
    cfg.checks = checks

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
    cfg.zip = z

    # [profile]
    profile = raw.get("profile", {})
    if "name" in profile:
        cfg.profile_name = profile["name"]

    return cfg
