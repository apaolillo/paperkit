# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Project-wide bibliography checks: unused entries per bib file.

Several build targets may share a bib file, so an entry is unused only if no
target that uses the file cites it. Which bib files a target uses and which
keys it cites come from its LaTeX output, never from scanning sources:

  * bibtex:   `\\bibdata{a,b}` and `\\citation{k1,k2}` in the .aux (and the
              .aux files it pulls in with `\\@input`); `\\citation{*}` is
              `\\nocite{*}`, which uses every entry.
  * biber:    the .bcf `<bcf:datasource>` and `<bcf:citekey>` elements.

Targets not built or checked in this run are resolved from their existing
.aux if it is up to date, else from a draft LaTeX pass into a scratch
directory. If neither works, the target is "not checked" and no entry it
might cite is reported as unused.
"""

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperkit.builder import BuildResult, run_latex
from paperkit.checks import CheckResult, CheckStatus, check_bibtex_tidy
from paperkit.config import PaperkitConfig

_DIM = "\033[2m"
_RESET = "\033[0m"

_CITATION_RE = re.compile(r"\\citation\{([^}]*)\}")
_ABX_CITE_RE = re.compile(r"\\abx@aux@cite\{[^}]*\}\{([^}]+)\}")
_BIBDATA_RE = re.compile(r"\\bibdata\{([^}]*)\}")
_INPUT_RE = re.compile(r"\\@input\{([^}]*)\}")
_BCF_DATASOURCE_RE = re.compile(r"<bcf:datasource\b[^>]*>([^<]+)</bcf:datasource>")
_BCF_CITEKEY_RE = re.compile(r"<bcf:citekey\b[^>]*>([^<]+)</bcf:citekey>")
_BIB_ENTRY_RE = re.compile(r"^\s*@(\w+)\s*\{\s*([^,\s{}]+)", re.MULTILINE)
# Bib "entries" that are not citable references.
_NON_ENTRY_TYPES = {"string", "preamble", "comment"}

# Only these files can change what a target cites, so they decide whether an
# existing .aux is still up to date.
_SOURCE_SUFFIXES = {
    ".tex",
    ".sty",
    ".cls",
    ".bib",
    ".bst",
    ".bbx",
    ".cbx",
    ".def",
    ".cfg",
    # Typst sources and Hayagriva bibliographies
    ".typ",
    ".yml",
    ".yaml",
}


@dataclass
class AuxData:
    """What a target's LaTeX run recorded about its bibliography."""

    bibdata: list[str] = field(default_factory=list)  # bib names as written
    citations: set[str] = field(default_factory=set)
    cite_all: bool = False  # \nocite{*}


@dataclass
class TargetUsage:
    """Bib files used and keys cited by one build target."""

    name: str
    bib_files: set[Path]
    citations: set[str]
    cite_all: bool
    origin: str  # "this run", "existing .aux", "draft pass"


def parse_aux(aux_path: Path) -> AuxData:
    """Parse an .aux file and the .aux files it includes with \\@input."""
    return _parse_aux(aux_path.resolve(), aux_path.resolve().parent, set())


def _parse_aux(aux_path: Path, base: Path, seen: set[Path]) -> AuxData:
    data = AuxData()
    if aux_path in seen or not aux_path.is_file():
        return data
    seen.add(aux_path)

    text = aux_path.read_text(errors="replace")
    for m in _BIBDATA_RE.finditer(text):
        data.bibdata += [b.strip() for b in m.group(1).split(",") if b.strip()]
    keys = [k for m in _CITATION_RE.finditer(text) for k in m.group(1).split(",")]
    keys += [m.group(1) for m in _ABX_CITE_RE.finditer(text)]
    _add_keys(data, keys)

    for m in _INPUT_RE.finditer(text):
        # Every \@input path, however deeply nested, is relative to the output
        # directory holding the main .aux.
        nested = _parse_aux((base / m.group(1).strip()).resolve(), base, seen)
        data.bibdata += [b for b in nested.bibdata if b not in data.bibdata]
        data.citations |= nested.citations
        data.cite_all = data.cite_all or nested.cite_all
    return data


def parse_bcf(bcf_path: Path) -> AuxData:
    """Parse biblatex's control file (.bcf), which biber reads."""
    data = AuxData()
    if not bcf_path.is_file():
        return data
    text = bcf_path.read_text(errors="replace")
    data.bibdata = [m.group(1).strip() for m in _BCF_DATASOURCE_RE.finditer(text)]
    _add_keys(data, [m.group(1) for m in _BCF_CITEKEY_RE.finditer(text)])
    return data


def _add_keys(data: AuxData, keys: list[str]) -> None:
    for key in (k.strip() for k in keys):
        if key == "*":
            data.cite_all = True
        elif key:
            data.citations.add(key)


def resolve_bib_file(root: Path, name: str) -> Path | None:
    """Project bib file for a \\bibdata / datasource name, or None.

    Names resolve against the project root (where paperkit points bibtex and
    biber). Files found only in the TeX tree (e.g. IEEEabrv) are not the
    project's and are left out.
    """
    path = root / name
    if path.suffix != ".bib":
        path = path.with_name(path.name + ".bib")
    return path.resolve() if path.is_file() else None


def query_citations(config: PaperkitConfig, main: str) -> dict[str, Any] | None:
    """What *main* cites, asked of typst itself: keys, and whether it cites everything.

    `typst query` evaluates the document without producing a PDF, so this is
    the Typst counterpart of reading an .aux: build-derived, never a regex
    over the sources. None when typst is missing or the document fails.
    """
    base = ["typst", "query", "--root", str(config.root), str(config.main_file(main))]
    try:
        keys = subprocess.run(
            [*base, "cite", "--field", "key"], capture_output=True, text=True, check=True
        )
        full = subprocess.run(
            [*base, "bibliography", "--field", "full"], capture_output=True, text=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    citations = {k.strip("<>") for k in json.loads(keys.stdout or "[]")}
    cite_all = any(json.loads(full.stdout or "[]")) if full.returncode == 0 else False
    return {"citations": sorted(citations), "cite_all": cite_all}


def write_citations(config: PaperkitConfig, main: str, output_dir: Path) -> Path | None:
    """Record *main*'s citations next to its PDF, for checks that run later."""
    data = query_citations(config, main)
    if data is None:
        return None
    path = output_dir / f"{main}.cites"
    path.write_text(json.dumps(data, indent=1) + "\n")
    return path


def usage_record(config: PaperkitConfig, name: str, directory: Path) -> Path:
    """The file a build leaves behind that says what *name* cited."""
    suffix = ".cites" if config.is_typst else ".aux"
    return directory / f"{name}{suffix}"


def _usage_from_cites(config: PaperkitConfig, name: str, cites: Path, origin: str) -> TargetUsage:
    data = json.loads(cites.read_text())
    bib_files = {(config.root / config.bib).resolve()} if config.bib else set()
    return TargetUsage(name, bib_files, set(data["citations"]), bool(data["cite_all"]), origin)


def usage_from_dir(
    config: PaperkitConfig,
    name: str,
    directory: Path,
    origin: str,
) -> TargetUsage | None:
    """Usage recorded in *directory*: <name>.aux (and .bcf with biber), or <name>.cites."""
    record = usage_record(config, name, directory)
    if not record.is_file():
        return None
    if config.is_typst:
        return _usage_from_cites(config, name, record, origin)
    aux = record
    data = parse_aux(aux)
    if config.biber:
        bcf = parse_bcf(directory / f"{name}.bcf")
        data.bibdata += bcf.bibdata
        data.citations |= bcf.citations
        data.cite_all = data.cite_all or bcf.cite_all
    bib_files = {p for b in data.bibdata if (p := resolve_bib_file(config.root, b))}
    return TargetUsage(name, bib_files, data.citations, data.cite_all, origin)


def _newest_source_mtime(config: PaperkitConfig, name: str, usage: TargetUsage) -> float:
    """Newest modification time of anything that can change *name*'s citations."""
    out_dir = (config.root / config.output_dir).resolve()
    paths = [config.main_file(name), *usage.bib_files]
    if config.bib:
        paths.append(config.root / config.bib)
    for d in config.content_dirs:
        for p in (config.root / d).rglob("*"):
            if p.suffix in _SOURCE_SUFFIXES and out_dir not in p.resolve().parents:
                paths.append(p)
    return max((p.stat().st_mtime for p in paths if p.is_file()), default=0.0)


def is_up_to_date(config: PaperkitConfig, usage: TargetUsage, aux: Path) -> bool:
    return aux.stat().st_mtime > _newest_source_mtime(config, usage.name, usage)


def draft_usage(config: PaperkitConfig, name: str) -> TargetUsage | None:
    """Citations of *name* without a real build.

    For Typst that is one `typst query`; for LaTeX, one draft pass into a
    scratch directory.

    No PDF is written (shell-escape tools such as minted still run), and the
    real output directory is not touched. None if the pass fails, including
    when the engine is not installed: the check is advisory, so a host
    without TeX reports "not checked" rather than failing the run.
    """
    if config.is_typst:
        data = query_citations(config, name)
        if data is None:
            return None
        bib_files = {(config.root / config.bib).resolve()} if config.bib else set()
        return TargetUsage(
            name, bib_files, set(data["citations"]), bool(data["cite_all"]), "typst query"
        )
    flag = "-no-pdf" if config.engine == "xelatex" else "-draftmode"
    with tempfile.TemporaryDirectory(prefix=f"paperkit-draft-{name}-") as tmp:
        try:
            rc = run_latex(
                config.engine,
                config.root / f"{name}.tex",
                Path(tmp),
                shell_escape=config.shell_escape,
                extra_args=[flag],
            )
        except FileNotFoundError:
            return None
        if rc != 0:
            return None
        return usage_from_dir(config, name, Path(tmp), "draft pass")


def resolve_other_targets(
    config: PaperkitConfig,
    known: dict[str, TargetUsage],
    skip: set[str],
) -> tuple[dict[str, TargetUsage], list[str]]:
    """Usage of every main not in *known*: (resolved usages, names not checked).

    Mains in *skip* (e.g. a failed build in this run) are not checked.
    """
    usages = dict(known)
    unchecked: list[str] = []
    for name in config.mains:
        if name in usages:
            continue
        if name in skip:
            unchecked.append(name)
            continue
        out_dir = config.root / config.output_dir / name
        usage = usage_from_dir(config, name, out_dir, "existing .aux")
        if usage and is_up_to_date(config, usage, usage_record(config, name, out_dir)):
            usages[name] = usage
            continue
        if config.checks.unused_bib.draft_pass:
            print(f"  {_DIM}citations of {name}: draft {config.engine} pass ...{_RESET}")
            usage = draft_usage(config, name)
            if usage:
                usages[name] = usage
                continue
        unchecked.append(name)
    return usages, unchecked


_HAYAGRIVA_KEY_RE = re.compile(r"^([A-Za-z0-9_:.-]+):", re.MULTILINE)


def bib_entry_keys(bib_path: Path) -> set[str]:
    """Entry keys of a BibTeX file, or of a Hayagriva YAML file (its top-level keys)."""
    text = bib_path.read_text(errors="replace")
    if bib_path.suffix.lower() in (".yml", ".yaml"):
        return set(_HAYAGRIVA_KEY_RE.findall(text))
    return {
        m.group(2).strip()
        for m in _BIB_ENTRY_RE.finditer(text)
        if m.group(1).lower() not in _NON_ENTRY_TYPES
    }


def unused_bib_checks(
    config: PaperkitConfig,
    usages: dict[str, TargetUsage],
    unchecked: list[str],
    focus: list[str],
) -> list[CheckResult]:
    """One "Unused bib entries" result per bib file used by the *focus* targets."""
    focus_usages = [usages[n] for n in focus if n in usages]
    configured = resolve_bib_file(config.root, config.bib) if config.bib else None
    bib_files = {p for u in focus_usages for p in u.bib_files}
    # A configured bib file no target declares (e.g. bibliography commented
    # out) is still checked against the focus targets' citations.
    legacy = configured is not None and not any(configured in u.bib_files for u in usages.values())
    if legacy and configured is not None:
        bib_files.add(configured)

    if not focus_usages or not bib_files:
        skipped = CheckResult(name="Unused bib entries")
        skipped.messages.append("Skipped (aux or bib file not found)")
        return [skipped]

    ignore = set(config.checks.unused_bib.ignore)
    root = config.root.resolve()
    multi = len(config.mains) > 1
    results = []
    for bib in sorted(bib_files):
        users = [u for u in usages.values() if bib in u.bib_files]
        if legacy and bib == configured:
            users = focus_usages
        rel = bib.relative_to(root) if bib.is_relative_to(root) else bib
        name = "Unused bib entries" if len(bib_files) == 1 else f"Unused bib entries ({rel})"
        results.append(_unused_result(name, bib, users, unchecked, ignore, multi))
    return results


def _unused_result(
    name: str,
    bib: Path,
    users: list[TargetUsage],
    unchecked: list[str],
    ignore: set[str],
    multi: bool,
) -> CheckResult:
    result = CheckResult(name=name)
    if any(u.cite_all for u in users):
        result.messages.append("All bib entries are cited (\\nocite{*})")
        return result
    cited = set().union(*(u.citations for u in users))
    not_cited = sorted(bib_entry_keys(bib) - cited - ignore)
    user_names = ", ".join(u.name for u in users)

    if not not_cited:
        result.messages.append("All bib entries are cited")
    elif unchecked:
        # Another target may cite these: say so, but never call them unused.
        result.show_details = True
        result.messages.append(
            f"{len(not_cited)} not cited by {user_names or 'the checked targets'}; "
            f"other targets not checked: {', '.join(unchecked)}",
        )
        result.messages.extend(f"  {key}" for key in not_cited)
    else:
        result.status = CheckStatus.WARNING
        if multi:
            result.messages.append(
                f"{len(not_cited)} unused bib entry/entries (cited by no target: {user_names}):",
            )
        else:
            result.messages.append(f"{len(not_cited)} unused bib entry/entries:")
        result.messages.extend(f"  {key}" for key in not_cited)
    return result


def project_bib_checks(
    config: PaperkitConfig,
    outputs: dict[str, BuildResult],
    focus: list[str],
    failed: set[str] | None = None,
) -> list[CheckResult]:
    """Bibliography checks for the bib files the *focus* targets use.

    *outputs* holds this run's build (or checked) output per target; other
    mains are resolved with resolve_other_targets.
    """
    results: list[CheckResult] = []
    if config.checks.unused_bib.enabled:
        known = {
            name: usage
            for name, out in outputs.items()
            if (usage := usage_from_dir(config, name, out.output_dir, "this run"))
        }
        usages, unchecked = resolve_other_targets(config, known, skip=failed or set())
        results += unused_bib_checks(config, usages, unchecked, focus)
    if config.checks.bibtex_tidy.enabled:
        results.append(check_bibtex_tidy(config))
    return results
