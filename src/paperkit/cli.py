"""Click CLI entry point for paperkit."""

import sys
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


@main.command()
@click.option("--no-docker", is_flag=True, help="Build on host instead of in Docker")
@click.option("--shell", is_flag=True, help="Open interactive shell in Docker container")
@click.pass_context
def build(ctx: click.Context, no_docker: bool, shell: bool) -> None:
    """Build the paper PDF."""
    config = _get_config(ctx)

    verbose = ctx.obj["verbose"]

    if shell:
        from paperkit.docker import build_image, run_in_docker

        click.echo(_header("\U0001f433 Building Docker image ..."))
        build_image(config, verbose=verbose)
        click.echo(_header("\U0001f4bb Opening interactive shell ..."))
        run_in_docker(config, "bash", interactive=True, verbose=verbose)
        return

    if no_docker:
        _build_host(config)
    else:
        _build_docker(config, verbose=verbose)


def _build_host(config: PaperkitConfig) -> None:
    """Build directly on the host."""
    from paperkit.builder import build_paper
    from paperkit.checks import run_all_checks
    from paperkit.report import get_environment_info, print_report

    click.echo(_header(f"\U0001f4c4 Building {config.main}.tex ..."))
    result = build_paper(config)

    if not result.success:
        sys.exit(1)

    env_info = get_environment_info(config, result)
    check_results = run_all_checks(config, result)
    print_report(result, check_results, env_info=env_info)


def _build_docker(config: PaperkitConfig, verbose: bool = False) -> None:
    """Build inside a Docker container."""
    from paperkit.docker import build_image, run_in_docker

    click.echo(_header("\U0001f433 Building Docker image ..."))
    build_image(config, verbose=verbose)

    click.echo(_header(f"\U0001f4c4 Building {config.main}.tex in Docker ..."))
    run_in_docker(config, "paperkit build --no-docker", verbose=verbose)


@main.command()
@click.pass_context
def check(ctx: click.Context) -> None:
    """Run checks only (on existing build output)."""
    config = _get_config(ctx)

    from paperkit.builder import BuildResult
    from paperkit.checks import run_all_checks
    from paperkit.report import get_environment_info, print_report

    output_dir = config.root / config.output_dir
    result = BuildResult(
        pdf=output_dir / f"{config.main}.pdf",
        log=output_dir / f"{config.main}.log",
        blg=output_dir / f"{config.main}.blg",
        aux=output_dir / f"{config.main}.aux",
        output_dir=output_dir,
        success=True,
    )

    # Verify at least the log exists
    log_path = output_dir / f"{config.main}.log"
    if not log_path.is_file():
        click.echo(f"No build output found in {output_dir}/. Run 'paperkit build' first.")
        sys.exit(1)

    click.echo(_header("\U0001f50d Running checks ..."))
    env_info = get_environment_info(config, result)
    check_results = run_all_checks(config, result)
    print_report(result, check_results, env_info=env_info)


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
