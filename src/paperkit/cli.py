# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved.
# SPDX-License-Identifier: MIT

"""Click CLI entry point for paperkit."""

import io
import os
import shlex
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

import click

from paperkit import reproducible, texlive
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
    """paperkit: reproducible builds and pre-submission checks for research papers."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["verbose"] = verbose


def _get_config(ctx: click.Context) -> PaperkitConfig:
    return load_config(ctx.obj.get("config_path"))


def _config_path(ctx: click.Context) -> Path:
    """The .paperkit.toml in use, for commands that edit it."""
    from paperkit.config import find_config

    return ctx.obj.get("config_path") or find_config()


def _default_jobs() -> int:
    return os.cpu_count() or 1


def _resolve_targets(config: PaperkitConfig, names: tuple[str, ...]) -> list[str]:
    """Map NAMES (with or without .tex) to entries of config.mains.

    With no names, returns all of config.mains. Exits with an error listing
    the known mains when a name doesn't match any of them.
    """
    if not names:
        return list(config.mains)
    targets = [n[:-4] if n.endswith(".tex") else n for n in names]
    unknown = [t for t in targets if t not in config.mains]
    if unknown:
        click.echo(f"Unknown main(s): {', '.join(unknown)}")
        click.echo(f"Known mains: {', '.join(config.mains)}")
        sys.exit(1)
    return targets


@main.command()
@click.argument("names", nargs=-1)
@click.option("--no-docker", is_flag=True, help="Build on host instead of in Docker")
@click.option(
    "--jobs",
    "-j",
    type=int,
    default=None,
    help=f"Parallel build workers (default: cpu_count = {_default_jobs()})",
)
@click.pass_context
def build(ctx: click.Context, names: tuple[str, ...], no_docker: bool, jobs: int | None) -> None:
    """Build the paper PDF (loops over config.mains).

    With no NAMES, builds every main in config.mains. NAMES may be given with
    or without the .tex extension; each must be one of config.mains. Building
    a single main prints the full detailed report instead of the summary table.
    """
    config = _get_config(ctx)
    # config.mains keeps every target: bibliography checks look at the targets
    # not being built too, when they share a bib file.
    targets = _resolve_targets(config, names)
    # Precedence: CLI --jobs > [build] jobs in .paperkit.toml > cpu_count.
    if jobs and jobs > 0:
        n_jobs = jobs
    elif config.jobs and config.jobs > 0:
        n_jobs = config.jobs
    else:
        n_jobs = _default_jobs()

    if no_docker:
        _build_host(config, targets, jobs=n_jobs)
    else:
        _build_docker(config, targets, names, jobs=n_jobs, verbose=ctx.obj["verbose"])


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


def _build_host(config: PaperkitConfig, targets: list[str], jobs: int = 1) -> None:
    """Build *targets* directly on the host (parallel by default for several)."""
    from paperkit.bibliography import project_bib_checks
    from paperkit.builder import BuildResult, build_paper
    from paperkit.checks import CheckResult, run_all_checks
    from paperkit.report import get_environment_info, print_multi_summary, print_report

    n = len(targets)
    runs: list[tuple[str, BuildResult, list[CheckResult]]] = []

    # Single target: keep the existing chatty flow (live "[k/4]" pass markers + full report).
    if n == 1:
        main = targets[0]
        click.echo(_header(f"\U0001f4c4 Building {main}.tex ..."))
        result = build_paper(config, main)
        if result.success:
            env_info = get_environment_info(config, result)
            bib_results = project_bib_checks(config, {main: result}, focus=[main])
            check_results = run_all_checks(config, result, bib_results)
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
        # Sequential fallback: same as parallel path but without the pool.
        for completed, main in enumerate(targets, start=1):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = build_paper(config, main)
                checks = run_all_checks(config, result) if result.log or result.pdf else []
            _emit_progress(completed, n, main, result.success, buf.getvalue())
            runs.append((main, result, checks))
    else:
        results_by_main: dict[str, tuple[str, BuildResult, list[CheckResult]]] = {}
        with ProcessPoolExecutor(max_workers=effective_jobs) as ex:
            futs = {ex.submit(_run_one, config, m): m for m in targets}
            completed = 0
            for fut in as_completed(futs):
                payload = fut.result()
                main = payload["main"]
                result = payload["result"]
                checks = payload["checks"]
                completed += 1
                _emit_progress(completed, n, main, result.success, payload["captured"])
                results_by_main[main] = (main, result, checks)
        # Reorder by target order for the summary table.
        runs = [results_by_main[m] for m in targets if m in results_by_main]

    print()
    built = {m: r for m, r, _ in runs if r.success}
    failed = {m for m, r, _ in runs if not r.success}
    shared = project_bib_checks(config, built, focus=targets, failed=failed)
    print_multi_summary(runs, shared)

    if not all(r.success for _, r, _ in runs):
        sys.exit(1)


def _emit_progress(k: int, n: int, main: str, success: bool, captured: str) -> None:
    """One-line completion marker; on failure also flush the captured per-build output."""
    width = len(str(n))
    marker = "\033[32m\u2714\033[0m" if success else "\033[31m\u2718\033[0m"
    click.echo(f"  [{k:>{width}}/{n}] {marker} {main}")
    if not success and captured:
        click.echo(captured)


def _build_docker(
    config: PaperkitConfig,
    targets: list[str],
    names: tuple[str, ...] = (),
    jobs: int = 1,
    verbose: bool = False,
) -> None:
    """Build inside a Docker container; the inner CLI invocation does the looping."""
    from paperkit.docker import build_image, run_in_docker

    click.echo(_header("\U0001f433 Building Docker image ..."))
    build_image(config, verbose=verbose)

    n = len(targets)
    label = f"{n} project(s)" if n != 1 else f"{targets[0]}.tex"
    click.echo(_header(f"\U0001f4c4 Building {label} in Docker ..."))
    # The image has no git, so resolve the build timestamp here and pass it in;
    # the inner paperkit then takes it from the environment.
    source_date = reproducible.resolve(config.source_date_epoch, config.root)
    if source_date.warning:
        click.echo(f"  {_DIM}warning: {source_date.warning}{_RESET}")
    # The inner invocation re-reads .paperkit.toml, so pass the selection along.
    rc = run_in_docker(
        config,
        f"paperkit build --no-docker --jobs {jobs}{_shell_args(names)}",
        verbose=verbose,
        env=reproducible.build_env(source_date),
    )
    if rc:
        sys.exit(rc)


def _shell_args(args: tuple[str, ...]) -> str:
    """Arguments quoted for the shell command run inside the container."""
    return "".join(f" {shlex.quote(a)}" for a in args)


@main.command()
@click.argument("names", nargs=-1)
@click.option("--no-docker", is_flag=True, help="Run checks on host instead of in Docker")
@click.pass_context
def check(ctx: click.Context, names: tuple[str, ...], no_docker: bool) -> None:
    """Run checks on existing build output and print full per-main reports.

    With no NAMES, checks every main in config.mains. NAMES may be given with
    or without the .tex extension; each must be one of config.mains. Checks
    run in the Docker image by default, so their tools (pdffonts,
    bibtex-tidy, ...) are the ones the build used, not the host's.
    """
    config = _get_config(ctx)
    targets = _resolve_targets(config, names)

    if no_docker:
        _check_host(config, targets)
    else:
        _check_docker(config, names, verbose=ctx.obj["verbose"])


def _check_docker(config: PaperkitConfig, names: tuple[str, ...], verbose: bool = False) -> None:
    """Run `paperkit check` inside the container."""
    from paperkit.docker import build_image, run_in_docker

    click.echo(_header("\U0001f433 Building Docker image ..."))
    build_image(config, verbose=verbose)
    rc = run_in_docker(config, f"paperkit check --no-docker{_shell_args(names)}", verbose=verbose)
    if rc:
        sys.exit(rc)


def _check_host(config: PaperkitConfig, targets: list[str]) -> None:
    """Run checks on the host, with the host's tools."""
    from paperkit.bibliography import project_bib_checks
    from paperkit.builder import BuildResult
    from paperkit.checks import CheckResult, run_all_checks
    from paperkit.report import get_environment_info, print_multi_summary, print_report

    outputs: dict[str, BuildResult] = {}
    for main in targets:
        per_main_dir = config.root / config.output_dir / main
        log_path = per_main_dir / f"{main}.log"
        if not log_path.is_file():
            click.echo(
                f"No build output for '{main}' in {per_main_dir}/. Run 'paperkit build' first.",
            )
            continue
        outputs[main] = BuildResult(
            pdf=per_main_dir / f"{main}.pdf",
            log=log_path,
            blg=per_main_dir / f"{main}.blg",
            aux=per_main_dir / f"{main}.aux",
            output_dir=per_main_dir,
            success=True,
        )
    if not outputs:
        sys.exit(1)

    # With one target, its bibliography results go into its report; with
    # several, they are shown once for the project after the per-target reports.
    single = len(outputs) == 1
    bib_results = project_bib_checks(config, outputs, focus=list(outputs))

    runs: list[tuple[str, BuildResult, list[CheckResult]]] = []
    for main, result in outputs.items():
        click.echo(_header(f"\U0001f50d Checking {main} ..."))
        env_info = get_environment_info(config, result)
        check_results = run_all_checks(config, result, bib_results if single else None)
        print_report(result, check_results, env_info=env_info)
        runs.append((main, result, check_results))

    if not single:
        print_multi_summary(runs, bib_results)


@main.command(name="zip")
@click.option(
    "--bbl/--no-bbl",
    default=None,
    help="Include each main's compiled bibliography (default: [zip] include_bbl)",
)
@click.pass_context
def zip_cmd(ctx: click.Context, bbl: bool | None) -> None:
    """Create submission archive.

    --bbl adds <main>.bbl next to <main>.tex, for publishers that compile the
    sources without running BibTeX. The build output must be up to date.
    """
    config = _get_config(ctx)

    from paperkit.archive import MissingBblError, create_zip, print_zip_summary

    click.echo(_header("\U0001f4e6 Creating submission archive ..."))
    try:
        result = create_zip(config, include_bbl=bbl)
    except MissingBblError as e:
        click.echo(f"  {e}", err=True)
        sys.exit(1)
    for warning in result.warnings:
        click.echo(f"  {_DIM}warning: {warning}{_RESET}")
    print_zip_summary(result.path)


@main.command()
@click.option("--no-docker", is_flag=True, help="Run on host instead of in Docker")
@click.option(
    "--sort/--no-sort",
    default=None,
    help="Sort entries by key and fields within entries "
    "(default: [checks] bibtex_tidy.sort, itself true)",
)
@click.pass_context
def bibtidy(ctx: click.Context, no_docker: bool, sort: bool | None) -> None:
    """Run bibtex-tidy on the bib file (in-place).

    --no-sort keeps the file's own entry and field order and applies the
    other defaults. Without the flag, [checks] bibtex_tidy.sort decides, so
    the tidiness check in `paperkit build` agrees with this command.
    """
    config = _get_config(ctx)
    if sort is not None:
        config.checks.bibtex_tidy.sort = sort

    if no_docker:
        _tidy_host(config)
    else:
        _tidy_docker(config, verbose=ctx.obj["verbose"])


@main.command(name="tidy", hidden=True)
@click.option("--no-docker", is_flag=True)
@click.option("--sort/--no-sort", default=None)
@click.pass_context
def tidy(ctx: click.Context, no_docker: bool, sort: bool | None) -> None:
    """Deprecated alias for `bibtidy`."""
    click.echo("warning: 'paperkit tidy' is now 'paperkit bibtidy'.", err=True)
    ctx.invoke(bibtidy, no_docker=no_docker, sort=sort)


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
    sort = config.checks.bibtex_tidy.sort
    tidy_args = profile.bibtex_tidy_args(sort=sort)

    how = "sorted" if sort else "unsorted"
    click.echo(_header(f"\U0001f9f9 Tidying {config.bib} ({how}) ..."))
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
    # The inner invocation re-reads .paperkit.toml, so pass the sort choice along.
    sort_flag = "--sort" if config.checks.bibtex_tidy.sort else "--no-sort"
    rc = run_in_docker(config, f"paperkit bibtidy --no-docker {sort_flag}", verbose=verbose)
    if rc:
        sys.exit(rc)


@main.command(name="texlive-update")
@click.option("--check", is_flag=True, help="Report the newest snapshot without editing the config")
@click.pass_context
def texlive_update(ctx: click.Context, check: bool) -> None:
    """Move [texlive] to the newest dated snapshot.

    Queries the snapshot archive, then rewrites `snapshot` and `tlpdb_sha512`
    in .paperkit.toml, leaving the rest of the file untouched. This is the
    only command that looks things up online; builds never do.
    """
    config_path = _config_path(ctx)
    click.echo(_header("\U0001f4c5 Looking up the newest TeX Live snapshot ..."))
    newest = texlive.latest_snapshot()
    if newest is None:
        click.echo("  no snapshot found (is the archive reachable?)", err=True)
        sys.exit(1)
    snapshot, digest = newest

    text = config_path.read_text()
    try:
        updated, previous = texlive.update_config_text(text, snapshot, digest)
    except ValueError as e:
        click.echo(f"  {e}", err=True)
        sys.exit(1)

    current = previous.get("snapshot", "")
    if current == snapshot:
        click.echo(f"  already on the newest snapshot ({snapshot})")
        return
    click.echo(f"  {current or 'unset'} -> {snapshot}")
    click.echo(f"  {_DIM}tlpdb_sha512 {digest}{_RESET}")
    if check:
        click.echo(f"  {_DIM}--check: {config_path.name} not modified{_RESET}")
        return
    config_path.write_text(updated)
    click.echo(f"  {_BOLD}\u2705 {config_path.name} updated{_RESET}; rebuild to pick it up")


def _texlive_block(mode: str) -> str:
    """The [texlive] section `paperkit init` writes."""
    if mode == "distro":
        return """# TeX Live comes from the base image's texlive-* packages. Note that the
# distro minted and latexminted do not work together on ubuntu:26.04; switch
# to the snapshot below if you use minted.
[texlive]
source = "distro"
"""
    collections = ", ".join(f'"{c}"' for c in texlive.DEFAULT_COLLECTIONS)
    return f"""# TeX Live from a dated upstream snapshot: the same package set on every
# image rebuild, and a working minted. `paperkit texlive-update` moves this
# to a newer snapshot; `source = "distro"` uses the base image's packages.
[texlive]
source = "upstream"
snapshot = "{texlive.KNOWN_GOOD_SNAPSHOT}"
tlpdb_sha512 = "{texlive.KNOWN_GOOD_TLPDB_SHA512}"
scheme = "{texlive.DEFAULT_SCHEME}"
collections = [{collections}]
"""


@main.command()
@click.option("--profile", default="acm", help="Profile to use (default: acm)")
@click.option(
    "--texlive",
    "texlive_mode",
    type=click.Choice(["snapshot", "distro"]),
    default="snapshot",
    help="TeX Live source for the new project (default: snapshot)",
)
def init(profile: str, texlive_mode: str) -> None:
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
base_image = "ubuntu:26.04"
image_name = "paper-builder"
extra_packages = []

{_texlive_block(texlive_mode)}
[checks]
non_ascii = true
trailing_whitespace = true
final_newline = true
unused_bib = true
font_embedding = true
no_type3 = true
overfull_boxes = true
bibtex_tidy = {{ enabled = true, version = "1.14.0" }}

# Page-count limits: leave fields unset to get an informational report only.
# Auto-detects the references and acknowledgments sections from the .aux file
# (English titles; override refs_pattern / ack_pattern if needed).
# [page_limits]
# total = 14            # max total pages (incl. references)
# before_refs = 12      # content before references must fit in 12 pages
# before_ack = 13       # content before acknowledgments must fit in 13 pages
# ack_counts_as_content = false   # true: acknowledgments count toward
#                                 # before_refs, as at venues that exempt
#                                 # only the references

[zip]
name = "main"
include = [
    "{{main}}.tex",
    "content/*.tex",
]
exclude = ["*.aux", "*.log", "*.out", "*.blg", "*.bbl"]
# Ship each main's compiled bibliography (<main>.bbl) next to its .tex, for
# publishers that compile without running BibTeX (e.g. Springer LNCS).
include_bbl = false

[profile]
name = "{profile}"
"""
    dest = Path.cwd() / ".paperkit.toml"
    if dest.exists():
        click.echo(f".paperkit.toml already exists at {dest}")
        sys.exit(1)
    dest.write_text(template)
    click.echo(f"\u2705 Created {dest}")
