from pathlib import Path
from typing import Optional

import typer

from iterecho import __version__
from iterecho.config import AppConfig, fmt_size
from iterecho.processing import FileProcessor
from iterecho.search import FileSearcher
from iterecho.security import SecurityEngine
from iterecho.tui import run_tui
from iterecho.utils.logging import get_logger, setup_logging

app = typer.Typer(
    name="iterecho",
    help="IterEcho - Secure File Processor with copy, concatenate and chunk modes.",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

logger = get_logger("cli")


def _run_processing(config: AppConfig, dry_run: bool = False) -> None:
    """Execute file processing pipeline for the given configuration."""
    setup_logging(verbose=config.verbose, quiet=config.quiet)

    security = SecurityEngine(config.base_dir, config.max_file_size)

    searcher = FileSearcher(config)
    files = searcher.find_files()

    if not files:
        logger.warning("No files found matching the specified criteria.")
        raise typer.Exit(0)

    logger.info(f"Found {len(files)} file(s).")

    if dry_run:
        logger.info("\n--dry-run: Files that would be processed:")
        for f in files:
            logger.info(f"  - {f.relative_path} ({fmt_size(f.size)})")
        raise typer.Exit(0)

    processor = FileProcessor(config, security=security)
    processor.process(files)

    logger.info("Processing complete!")


def _version_callback(value: bool) -> None:
    """Print the package version and exit when ``--version`` is passed.

    Registered with ``is_eager=True`` so it runs before subcommand resolution,
    which lets ``iterecho --version`` work even without a subcommand.
    """
    if value:
        typer.echo(f"IterEcho v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    _version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    unsafe: bool = typer.Option(False, "--unsafe", help="Allow warning-level extensions"),
    extensions: str = typer.Option(
        ".txt", "--extensions", help="Comma-separated extensions (e.g. .txt,.log)"
    ),
    base_dir: Path = typer.Option(None, "--base-dir", help="Base directory for file search"),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Output directory (defaults to base directory)"
    ),
    output_extension: str = typer.Option(
        ".txt", "--output-extension", help="Output file extension"
    ),
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="Search recursively into subdirectories"
    ),
    name_filter: Optional[str] = typer.Option(
        None, "--name-filter", help="Substring to match in filenames (e.g. 'log')"
    ),
    max_file_size: str = typer.Option(
        "100M", "--max-file-size", help="Maximum file size (e.g. 100M, 1G)"
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing files"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose (DEBUG) logging"),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress all output except warnings and errors"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be processed without performing the operation"
    ),
) -> None:
    """IterEcho - Secure File Processor with copy, concatenate and chunk modes.

    Shared options apply to all subcommands and can be placed before or after
    the subcommand name.
    """
    if base_dir is None:
        base_dir = Path.cwd()

    config = AppConfig()
    config.unsafe = unsafe
    config.extensions = extensions
    config.base_dir = base_dir
    config.output_dir = output_dir
    config.output_extension = output_extension
    config.recursive = recursive
    config.name_filter = name_filter
    config.max_file_size = max_file_size
    config.overwrite = overwrite
    config.verbose = verbose
    config.quiet = quiet

    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["dry_run"] = dry_run


@app.command(name="copy")
def copy_mode(
    ctx: typer.Context,
    follow_symlinks: bool = typer.Option(False, "--follow-symlinks", help="Follow symbolic links"),
) -> None:
    """Copy files with name sanitization, preserving directory structure."""
    config = ctx.obj["config"]
    config.mode = "copy"
    config.follow_symlinks = follow_symlinks
    _run_processing(config, ctx.obj["dry_run"])


@app.command(name="concatenate")
def concatenate_mode(
    ctx: typer.Context,
    output_file: Optional[Path] = typer.Option(
        None, "--output-file", help="Output file name (overrides prefix)"
    ),
    output_prefix: str = typer.Option(
        "concatenated", "--output-prefix", help="Prefix for the output file name"
    ),
) -> None:
    """Combine multiple files into a single output file."""
    config = ctx.obj["config"]
    config.mode = "concatenate"
    config.output_file = output_file
    config.output_prefix = output_prefix
    if output_file is not None:
        logger.info(f"--output-file set to '{output_file}'; --output-prefix is ignored.")
    _run_processing(config, ctx.obj["dry_run"])


@app.command(name="chunk")
def chunk_mode(
    ctx: typer.Context,
    chunk_size: str = typer.Option(
        "50M", "--chunk-size", help="Maximum size per chunk (e.g. 10M, 50M, 1G)"
    ),
    output_prefix: str = typer.Option(
        "chunk", "--output-prefix", help="Prefix for chunk file names"
    ),
    follow_symlinks: bool = typer.Option(False, "--follow-symlinks", help="Follow symbolic links"),
) -> None:
    """Split combined content into multiple chunks by size."""
    config = ctx.obj["config"]
    config.mode = "chunk"
    config.chunk_size = chunk_size
    config.output_prefix = output_prefix
    config.follow_symlinks = follow_symlinks
    _run_processing(config, ctx.obj["dry_run"])


@app.command(name="interactive")
def interactive_mode() -> None:
    """Interactive TUI mode for step-by-step configuration (ignores shared CLI options)."""
    setup_logging()
    config = run_tui()
    _run_processing(config, dry_run=False)


if __name__ == "__main__":
    app()
