"""LaTeX build pipeline (pdflatex, lualatex, xelatex + bibtex/biber)."""

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

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
    output_dir: Path = field(default_factory=lambda: Path("out"))
    success: bool = False


def run_latex(engine: str, tex_file: Path, output_dir: Path, shell_escape: bool = True) -> int:
    """Run a single LaTeX pass (pdflatex, lualatex, or xelatex). Returns exit code."""
    cmd = [
        engine,
        "-interaction=nonstopmode",
        f"-output-directory={output_dir}",
    ]
    if shell_escape:
        cmd.append("-shell-escape")
    cmd.append(str(tex_file))

    result = subprocess.run(cmd, capture_output=True)
    return result.returncode


def run_bibtex(aux_file: Path, bib_search_dir: Path) -> int:
    """Run bibtex with BIBINPUTS pointing to *bib_search_dir*. Returns exit code."""
    env = os.environ.copy()
    env["BIBINPUTS"] = f"{bib_search_dir}:"

    result = subprocess.run(
        ["bibtex", aux_file.stem],
        cwd=aux_file.parent,
        env=env,
        capture_output=True,
    )
    return result.returncode


def run_biber(jobname: str, output_dir: Path, project_root: Path) -> int:
    """Run biber from the project root with output in *output_dir*. Returns exit code."""
    result = subprocess.run(
        ["biber", f"--output-directory={output_dir}", jobname],
        cwd=project_root,
        capture_output=True,
    )
    return result.returncode


def build_paper(config: PaperkitConfig, main: str | None = None) -> BuildResult:
    """Orchestrate the full build for one main: N LaTeX passes with bibtex/biber after pass 1."""
    if main is None:
        main = config.main
    root = config.root
    output_dir = root / config.output_dir / main
    output_dir.mkdir(parents=True, exist_ok=True)

    tex_file = root / f"{main}.tex"
    result = BuildResult(output_dir=output_dir)

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
                run_biber(main, output_dir, root)
            else:
                aux = output_dir / f"{main}.aux"
                run_bibtex(aux, root)

        step += 1
        label = f"pass {i}"
        if i == config.passes and config.passes >= 4:
            label += " \u2013 pbalance"
        print(f"  {_DIM}[{step}/{total_steps}]{_RESET} {config.engine} ({label}) ...")
        run_latex(config.engine, tex_file, output_dir, shell_escape=config.shell_escape)

    # Check outputs
    pdf_path = output_dir / f"{main}.pdf"
    log_path = output_dir / f"{main}.log"
    blg_path = output_dir / f"{main}.blg"
    aux_path = output_dir / f"{main}.aux"

    result.log = log_path if log_path.is_file() else None
    result.blg = blg_path if blg_path.is_file() else None
    result.aux = aux_path if aux_path.is_file() else None

    if pdf_path.is_file():
        result.pdf = pdf_path
        result.success = True
        dest = root / f"{main}.pdf"
        shutil.copy2(pdf_path, dest)
        print(f"  {_GREEN}\u2714{_RESET} {_BOLD}{main}.pdf{_RESET}")

        # Best-effort: dump LaTeX-free title and abstract next to the PDF for
        # easy paste into submission systems (HotCRP, EasyChair, ...).
        from paperkit.text_export import print_text_exports, write_text_exports

        try:
            print_text_exports(write_text_exports(config, main, output_dir))
        except Exception as exc:  # noqa: BLE001 \u2014 never fail the build for this
            print(f"  {_DIM}(text export skipped: {exc}){_RESET}")
    else:
        print(f"  {_RED}\u2718 ERROR: {main}.pdf was not produced{_RESET}")
        if log_path.is_file():
            print(f"    See {log_path} for details")

    return result
