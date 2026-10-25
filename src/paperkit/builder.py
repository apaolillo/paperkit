# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""LaTeX build pipeline (pdflatex, lualatex, xelatex + bibtex/biber)."""

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from paperkit import reproducible
from paperkit.config import PaperkitConfig

# ANSI
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


@dataclass
class BuildResult:
    """Result of a paper build."""

    pdf: Path | None = None
    log: Path | None = None
    blg: Path | None = None
    aux: Path | None = None
    # Typst builds: the citations recorded at build time, and the exact
    # sources the compilation read.
    cites: Path | None = None
    deps: Path | None = None
    output_dir: Path = field(default_factory=lambda: Path("out"))
    success: bool = False


def run_latex(
    engine: str,
    tex_file: Path,
    output_dir: Path,
    shell_escape: bool = True,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
    prelude: str = "",
) -> int:
    """Run a single LaTeX pass (pdflatex, lualatex, or xelatex). Returns exit code.

    *prelude* is TeX code executed before the main file is read; the job name
    is then set explicitly, since the engine would otherwise name the job
    after that code instead of the file.
    """
    cmd = [
        engine,
        "-interaction=nonstopmode",
        f"-output-directory={output_dir}",
    ]
    if shell_escape:
        cmd.append("-shell-escape")
    cmd += extra_args or []
    if prelude:
        cmd.append(f"-jobname={tex_file.stem}")
        cmd.append(f"{prelude}\\input{{{tex_file}}}")
    else:
        cmd.append(str(tex_file))

    result = subprocess.run(cmd, capture_output=True, env=_environment(env))
    return result.returncode


def _environment(extra: dict[str, str] | None) -> dict[str, str]:
    """The caller's environment plus *extra*."""
    env = os.environ.copy()
    env.update(extra or {})
    return env


def run_bibtex(
    aux_file: Path, bib_search_dir: Path, extra_env: dict[str, str] | None = None
) -> int:
    """Run bibtex with BIBINPUTS pointing to *bib_search_dir*. Returns exit code."""
    env = _environment(extra_env)
    env["BIBINPUTS"] = f"{bib_search_dir}:"

    result = subprocess.run(
        ["bibtex", aux_file.stem],
        cwd=aux_file.parent,
        env=env,
        capture_output=True,
    )
    return result.returncode


def run_biber(
    jobname: str,
    output_dir: Path,
    project_root: Path,
    extra_env: dict[str, str] | None = None,
) -> int:
    """Run biber from the project root with output in *output_dir*. Returns exit code."""
    result = subprocess.run(
        ["biber", f"--output-directory={output_dir}", jobname],
        cwd=project_root,
        capture_output=True,
        env=_environment(extra_env),
    )
    return result.returncode


def typst_command(config: PaperkitConfig, main: str, output_dir: Path) -> list[str]:
    """The `typst compile` invocation for *main*, from the [typst] table."""
    tc = config.typst
    cmd = [
        "typst",
        "compile",
        "--root",
        str(config.root),
        "--diagnostic-format",
        "short",
        "--deps",
        str(output_dir / f"{main}.deps"),
        "--deps-format",
        "json",
    ]
    if tc.ignore_system_fonts:
        cmd.append("--ignore-system-fonts")
    for d in tc.fonts:
        cmd += ["--font-path", str(config.root / d)]
    if tc.pdf_standard:
        cmd += ["--pdf-standard", tc.pdf_standard]
    cmd += tc.extra_args
    cmd += [str(config.main_file(main)), str(output_dir / f"{main}.pdf")]
    return cmd


def run_typst(config: PaperkitConfig, main: str, output_dir: Path, env: dict[str, str]) -> int:
    """One Typst compilation; its diagnostics become <main>.log behind a banner.

    Typst has no log file of its own. The first line names the compiler, as
    the first line of a LaTeX log does, so the report and the toolchain check
    read both the same way. Returns the exit code.
    """
    banner = subprocess.run(["typst", "--version"], capture_output=True, text=True).stdout.strip()
    proc = subprocess.run(
        typst_command(config, main, output_dir),
        capture_output=True,
        text=True,
        env=_environment(env),
    )
    (output_dir / f"{main}.log").write_text(f"{banner}\n{proc.stderr}{proc.stdout}")
    return proc.returncode


def _build_typst(
    config: PaperkitConfig,
    main: str,
    output_dir: Path,
    env: dict[str, str],
) -> BuildResult:
    from paperkit.bibliography import write_citations

    result = BuildResult(output_dir=output_dir)
    print(f"  {_DIM}[1/1]{_RESET} typst compile ...")
    run_typst(config, main, output_dir, env)
    result.log = output_dir / f"{main}.log"
    deps = output_dir / f"{main}.deps"
    result.deps = deps if deps.is_file() else None
    result.cites = write_citations(config, main, output_dir)
    return result


def build_paper(config: PaperkitConfig, main: str | None = None) -> BuildResult:
    """Orchestrate the full build for one main: N LaTeX passes with bibtex/biber after pass 1."""
    if main is None:
        main = config.main
    root = config.root
    output_dir = root / config.output_dir / main
    output_dir.mkdir(parents=True, exist_ok=True)

    tex_file = config.main_file(main)
    result = BuildResult(output_dir=output_dir)

    # One timestamp for the whole pipeline, so rebuilds are byte-identical.
    source_date = reproducible.resolve(config.source_date_epoch, root)
    if source_date.warning:
        print(f"  {_DIM}warning: {source_date.warning}{_RESET}")
    env = reproducible.build_env(source_date)

    if config.is_typst:
        result = _build_typst(config, main, output_dir, env)
        return _finish(config, main, output_dir, result)
    prelude = (
        reproducible.trailer_id_code(config.engine, source_date, main)
        if reproducible.needs_trailer_id(config.engine)
        else ""
    )

    use_bib = config.bibtex or config.biber
    bib_tool = "biber" if config.biber else "bibtex"
    total_steps = config.passes + (1 if use_bib else 0)
    step = 0

    for i in range(1, config.passes + 1):
        # Run bibliography tool after pass 1
        if use_bib and i == 2:
            step += 1
            print(f"  {_DIM}[{step}/{total_steps}]{_RESET} {bib_tool} ...")
            if config.biber:
                run_biber(main, output_dir, root, env)
            else:
                aux = output_dir / f"{main}.aux"
                run_bibtex(aux, root, env)

        step += 1
        label = f"pass {i}"
        if i == config.passes and config.passes >= 4:
            label += " \u2013 pbalance"
        print(f"  {_DIM}[{step}/{total_steps}]{_RESET} {config.engine} ({label}) ...")
        run_latex(
            config.engine,
            tex_file,
            output_dir,
            shell_escape=config.shell_escape,
            env=env,
            prelude=prelude,
        )

    # Check outputs
    log_path = output_dir / f"{main}.log"
    blg_path = output_dir / f"{main}.blg"
    aux_path = output_dir / f"{main}.aux"

    result.log = log_path if log_path.is_file() else None
    result.blg = blg_path if blg_path.is_file() else None
    result.aux = aux_path if aux_path.is_file() else None
    return _finish(config, main, output_dir, result)


def _finish(
    config: PaperkitConfig, main: str, output_dir: Path, result: BuildResult
) -> BuildResult:
    """Record the PDF, copy it to the root, and export the texts; common to both engines."""
    root = config.root
    pdf_path = output_dir / f"{main}.pdf"
    log_path = output_dir / f"{main}.log"

    if pdf_path.is_file():
        result.pdf = pdf_path
        result.success = True
        dest = root / f"{main}.pdf"
        shutil.copy2(pdf_path, dest)
        print(f"  {_GREEN}\u2714{_RESET} {_BOLD}{main}.pdf{_RESET}")

        # Best-effort: dump LaTeX-free title and abstract next to the PDF for
        # easy paste into submission systems (HotCRP, EasyChair, ...).
        from paperkit.text_export import print_text_exports, write_text_exports

        print_text_exports(write_text_exports(config, main, output_dir))
    else:
        print(f"  {_RED}\u2718 ERROR: {main}.pdf was not produced{_RESET}")
        if log_path.is_file():
            print(f"    See {log_path} for details")

    return result
