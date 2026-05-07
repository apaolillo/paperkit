"""Click CLI entry point for paperkit."""

import io
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

import click

from paperkit.config import PaperkitConfig, load_config

# ANSI
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_RESET = "\033[0m"


def _header(msg: str) -> str:
    return f"{_BOLD}{_CYAN}{msg}{_RESET}"


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Path to .paperkit.toml (default: auto-detect)",
)
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output (Docker commands, etc.)")
@click.pass_context
def main(ctx: click.Context, config_path: Path | None, verbose: bool) -> None:
    """paperkit — reusable build toolkit for LaTeX papers."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["verbose"] = verbose


def _get_config(ctx: click.Context) -> PaperkitConfig:
    return load_config(ctx.obj.get("config_path"))


def _default_jobs() -> int:
    return os.cpu_count() or 1


@main.command()
@click.option("--no-docker", is_flag=True, help="Build on host instead of in Docker")
@click.option(
    "--jobs",
    "-j",
    type=int,
    default=None,
    help=f"Parallel build workers (default: cpu_count = {_default_jobs()})",
)
@click.pass_context
def build(ctx: click.Context, no_docker: bool, jobs: int | None) -> None:
    """Build the paper PDF (loops over config.mains)."""
    config = _get_config(ctx)
    n_jobs = jobs if jobs and jobs > 0 else _default_jobs()

    if no_docker:
        _build_host(config, jobs=n_jobs)
    else:
        _build_docker(config, jobs=n_jobs, verbose=ctx.obj["verbose"])


@main.command()
@click.pass_context
def shell(ctx: click.Context) -> None:
    """Open an interactive bash shell in the Docker container."""
    from paperkit.docker import build_image, run_in_docker

    config = _get_config(ctx)
    verbose = ctx.obj["verbose"]

    click.echo(_header("\U0001f433 Building Docker image ..."))
    build_image(config, verbose=verbose)
    click.echo(_header("\U0001f4bb Opening shell (project mounted at /paper) ..."))
    run_in_docker(config, "bash", interactive=True, verbose=verbose)


def _run_one(config: PaperkitConfig, main: str) -> dict:
    """Worker entry: build one main + run checks, capturing per-build output.

    Top-level function so it can be pickled by ProcessPoolExecutor. Returned
    dict bundles BuildResult, check results, env info, and the captured
    stdout that build_paper would have printed live.
    """
    from paperkit.builder import build_paper
    from paperkit.checks import run_all_checks
    from paperkit.report import get_environment_info

    buf = io.StringIO()
    with redirect_stdout(buf):
        result = build_paper(config, main)
        check_results = run_all_checks(config, result) if result.log or result.pdf else []
        env_info = get_environment_info(config, result) if result.log else {}
    return {
        "main": main,
        "result": result,
        "checks": check_results,
        "env_info": env_info,
        "captured": buf.getvalue(),
    }


def _build_host(config: PaperkitConfig, jobs: int = 1) -> None:
    """Build directly on the host (parallel by default for multi-main)."""
    from paperkit.builder import build_paper
    from paperkit.checks import run_all_checks
    from paperkit.report import get_environment_info, print_multi_summary, print_report

    n = len(config.mains)
    runs: list[tuple] = []  # type: ignore[type-arg]

    # Single-main: keep the existing chatty flow (live "[k/4]" pass markers + full report).
    if n == 1:
        main = config.mains[0]
        click.echo(_header(f"\U0001f4c4 Building {main}.tex ..."))
        result = build_paper(config, main)
        if result.success:
            env_info = get_environment_info(config, result)
            check_results = run_all_checks(config, result)
            print_report(result, check_results, env_info=env_info)
            runs.append((main, result, check_results))
        else:
            runs.append((main, result, []))
            sys.exit(1)
        return

    # Multi-main: pool workers, lightweight progress, summary at the end.
    effective_jobs = max(1, min(jobs, n))
    click.echo(_header(f"\U0001f4c4 Building {n} project(s) (jobs={effective_jobs}) ..."))

    if effective_jobs == 1:
        # Sequential fallback — same as parallel path but without the pool.
        completed = 0
        for main in config.mains:
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = build_paper(config, main)
                checks = run_all_checks(config, result) if result.log or result.pdf else []
                env_info = get_environment_info(config, result) if result.log else {}
            completed += 1
            _emit_progress(completed, n, main, result.success, buf.getvalue())
            runs.append((main, result, checks))
    else:
        results_by_main: dict[str, tuple] = {}  # type: ignore[type-arg]
        with ProcessPoolExecutor(max_workers=effective_jobs) as ex:
            futs = {ex.submit(_run_one, config, m): m for m in config.mains}
            completed = 0
            for fut in as_completed(futs):
                payload = fut.result()
                main = payload["main"]
                result = payload["result"]
                checks = payload["checks"]
                completed += 1
                _emit_progress(completed, n, main, result.success, payload["captured"])
                results_by_main[main] = (main, result, checks)
        # Reorder by config.mains for the summary table.
        runs = [results_by_main[m] for m in config.mains if m in results_by_main]

    print()
    print_multi_summary(runs)

    if not all(r.success for _, r, _ in runs):
        sys.exit(1)


def _emit_progress(k: int, n: int, main: str, success: bool, captured: str) -> None:
    """One-line completion marker; on failure also flush the captured per-build output."""
    width = len(str(n))
    marker = f"\033[32m✔\033[0m" if success else f"\033[31m✘\033[0m"
    click.echo(f"  [{k:>{width}}/{n}] {marker} {main}")
    if not success and captured:
        click.echo(captured)


def _build_docker(config: PaperkitConfig, jobs: int = 1, verbose: bool = False) -> None:
    """Build inside a Docker container — the inner CLI invocation does the looping."""
    from paperkit.docker import build_image, run_in_docker

    click.echo(_header("\U0001f433 Building Docker image ..."))
    build_image(config, verbose=verbose)

    n = len(config.mains)
    label = f"{n} project(s)" if n != 1 else f"{config.main}.tex"
    click.echo(_header(f"\U0001f4c4 Building {label} in Docker ..."))
    run_in_docker(config, f"paperkit build --no-docker --jobs {jobs}", verbose=verbose)


@main.command()
@click.argument("names", nargs=-1)
@click.pass_context
def check(ctx: click.Context, names: tuple[str, ...]) -> None:
    """Run checks on existing build output and print full per-main reports.

    With no NAMES, checks every main in config.mains. NAMES may be given with
    or without the .tex extension; each must be one of config.mains.
    """
    config = _get_config(ctx)

    from paperkit.builder import BuildResult
    from paperkit.checks import CheckResult, run_all_checks
    from paperkit.report import get_environment_info, print_multi_summary, print_report

    if names:
        targets = [n[:-4] if n.endswith(".tex") else n for n in names]
        unknown = [t for t in targets if t not in config.mains]
        if unknown:
            click.echo(f"Unknown main(s): {', '.join(unknown)}")
            click.echo(f"Known mains: {', '.join(config.mains)}")
            sys.exit(1)
    else:
        targets = list(config.mains)

    runs: list[tuple[str, BuildResult, list[CheckResult]]] = []

    for main in targets:
        per_main_dir = config.root / config.output_dir / main
        log_path = per_main_dir / f"{main}.log"
        if not log_path.is_file():
            click.echo(f"No build output for '{main}' in {per_main_dir}/. Run 'paperkit build' first.")
            continue
        result = BuildResult(
            pdf=per_main_dir / f"{main}.pdf",
            log=log_path,
            blg=per_main_dir / f"{main}.blg",
            aux=per_main_dir / f"{main}.aux",
            output_dir=per_main_dir,
            success=True,
        )
        click.echo(_header(f"\U0001f50d Checking {main} ..."))
        env_info = get_environment_info(config, result)
        check_results = run_all_checks(config, result)
        print_report(result, check_results, env_info=env_info)
        runs.append((main, result, check_results))

    if not runs:
        sys.exit(1)
    if len(runs) > 1:
        print_multi_summary(runs)


@main.command(name="zip")
@click.pass_context
def zip_cmd(ctx: click.Context) -> None:
    """Create submission archive."""
    config = _get_config(ctx)

    from paperkit.archive import create_zip, print_zip_summary

    click.echo(_header("\U0001f4e6 Creating submission archive ..."))
    zip_path = create_zip(config)
    print_zip_summary(zip_path)


@main.command()
@click.option("--no-docker", is_flag=True, help="Run on host instead of in Docker")
@click.pass_context
def tidy(ctx: click.Context, no_docker: bool) -> None:
    """Run bibtex-tidy on the bib file (in-place)."""
    config = _get_config(ctx)

    if no_docker:
        _tidy_host(config)
    else:
        _tidy_docker(config, verbose=ctx.obj["verbose"])


def _tidy_host(config: PaperkitConfig) -> None:
    """Run bibtex-tidy directly on the host."""
    import shutil
    import subprocess

    from paperkit.profiles import get_profile

    bib_path = config.root / config.bib if config.bib else None
    if not bib_path or not bib_path.is_file():
        click.echo(f"Bib file not found: {config.bib}")
        sys.exit(1)

    if not shutil.which("bibtex-tidy"):
        click.echo("bibtex-tidy not found. Install it with: npm install -g bibtex-tidy")
        sys.exit(1)

    profile = get_profile(config)
    tidy_args = profile.bibtex_tidy_args()

    click.echo(_header(f"\U0001f9f9 Tidying {config.bib} ..."))
    proc = subprocess.run(
        ["bibtex-tidy", *tidy_args, str(bib_path)],
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        click.echo(f"bibtex-tidy failed (exit {proc.returncode})")
        if proc.stderr:
            click.echo(proc.stderr)
        sys.exit(1)

    # Report results
    duplicates = [line for line in proc.stdout.splitlines() if "DUPLICATE_ENTRY" in line]
    if duplicates:
        click.echo(f"  {_DIM}Duplicates found:{_RESET}")
        for line in duplicates:
            click.echo(f"    {line.replace('DUPLICATE_ENTRY: ', '')}")

    click.echo(f"  {_BOLD}\u2705 {config.bib} tidied{_RESET}")


def _tidy_docker(config: PaperkitConfig, verbose: bool = False) -> None:
    """Run bibtex-tidy inside the Docker container."""
    from paperkit.docker import build_image, run_in_docker

    click.echo(_header("\U0001f433 Building Docker image ..."))
    build_image(config, verbose=verbose)

    click.echo(_header(f"\U0001f9f9 Tidying {config.bib} in Docker ..."))
    run_in_docker(config, "paperkit tidy --no-docker", verbose=verbose)


@main.command()
@click.option("--profile", default="acm", help="Profile to use (default: acm)")
def init(profile: str) -> None:
    """Generate a .paperkit.toml template."""
    template = f"""[project]
main = "main"                              # main .tex file (without extension)
content_dirs = ["content"]
bib = "references.bib"

[build]
engine = "pdflatex"
passes = 3
shell_escape = true
bibtex = true
output_dir = "out"

[docker]
base_image = "ubuntu:25.04"
image_name = "paper-builder"
extra_packages = []

[checks]
non_ascii = true
trailing_whitespace = true
final_newline = true
unused_bib = true
font_embedding = true
overfull_boxes = true
bibtex_tidy = {{ enabled = true, version = "1.14.0" }}

[zip]
name = "main"
include = [
    "{{main}}.tex",
    "content/*.tex",
]
exclude = ["*.aux", "*.log", "*.out", "*.blg", "*.bbl"]

[profile]
name = "{profile}"
"""
    dest = Path.cwd() / ".paperkit.toml"
    if dest.exists():
        click.echo(f".paperkit.toml already exists at {dest}")
        sys.exit(1)
    dest.write_text(template)
    click.echo(f"\u2705 Created {dest}")
