from __future__ import annotations

from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from iterecho.config import AppConfig, Mode, fmt_size

console = Console()


def _typed_prompt(
    prompt: str,
    *,
    default: str = "",
    required: bool = False,
    validate: str | None = None,
) -> str:
    while True:
        try:
            val = Prompt.ask(prompt, default=default) if default else Prompt.ask(prompt)
            val = val.strip()
            if required and not val:
                console.print("[red]This field is required![/red]")
                continue
            if validate == "mode" and val.lower() not in {m.value for m in Mode}:
                console.print("[red]Mode must be copy, concatenate, or chunk.[/red]")
                continue
            return val
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Operation cancelled.[/yellow]")
            raise typer.Exit(0) from None


def _confirm_prompt(text: str, *, default: bool = False) -> bool:
    try:
        return Confirm.ask(text, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Operation cancelled.[/yellow]")
        raise typer.Exit(0) from None


def run_tui() -> AppConfig:
    """Run the interactive text-based user interface."""
    from iterecho import __version__

    console.print(
        Panel.fit(
            f"IterEcho v{__version__} - Secure File Processor",
            subtitle="Interactive Mode",
            box=box.HEAVY,
        )
    )

    config = AppConfig()

    # ── Base directory ─────────────────────────────────────────────
    while True:
        try:
            raw = _typed_prompt("Base directory", default=str(Path.cwd()))
            config.base_dir = raw
            break
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")

    # ── Unsafe mode ────────────────────────────────────────────────
    config.unsafe = _confirm_prompt("Allow warning-level extensions?", default=False)

    # ── Extensions ─────────────────────────────────────────────────
    while True:
        try:
            config.extensions = _typed_prompt(
                "Extensions (comma-separated, e.g. .txt,.log)",
                default=".txt",
                required=True,
            )
            break
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")

    # ── Mode ───────────────────────────────────────────────────────
    while True:
        try:
            config.mode = _typed_prompt(
                "Mode (copy/concatenate/chunk)",
                default="concatenate",
                validate="mode",
            ).lower()
            break
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")

    # ── Output directory ───────────────────────────────────────────
    raw = _typed_prompt("Output directory (optional)", default="")
    config.output_dir = Path(raw).resolve() if raw.strip() else None

    config.output_extension = _typed_prompt("Output extension", default=".txt")
    config.recursive = _confirm_prompt("Recursive search?", default=True)

    # ── Max file size ──────────────────────────────────────────────
    while True:
        try:
            config.max_file_size = _typed_prompt(
                "Maximum file size (e.g. 200M, 1G)", default="100M"
            )
            break
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")

    config.overwrite = _confirm_prompt("Overwrite existing files?", default=False)

    # ── Mode-specific questions ────────────────────────────────────
    if config.mode is Mode.COPY:
        config.follow_symlinks = _confirm_prompt("Follow symbolic links?", default=False)
    elif config.mode is Mode.CONCATENATE:
        config.output_prefix = _typed_prompt("Output file prefix", default="concatenated")
        output_file = _typed_prompt("Output file name (optional)", default="")
        config.output_file = Path(output_file) if output_file else None
    elif config.mode is Mode.CHUNK:
        while True:
            try:
                config.chunk_size = _typed_prompt(
                    "Maximum chunk size (e.g. 10M, 50M, 1G)", default="50M"
                )
                break
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
        config.output_prefix = _typed_prompt("Chunk prefix", default="chunk")
        config.follow_symlinks = _confirm_prompt("Follow symbolic links?", default=False)

    # ── Summary table ──────────────────────────────────────────────
    table = Table(box=box.SIMPLE, title="Configuration Summary")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Base directory", str(config.base_dir))
    table.add_row("Extensions", ", ".join(config.extensions))
    table.add_row("Mode", config.mode.value.upper())

    if config.mode is Mode.COPY:
        table.add_row("Follow symlinks", "Yes" if config.follow_symlinks else "No")
    elif config.mode is Mode.CONCATENATE:
        table.add_row("Prefix", config.output_prefix)
        table.add_row("Output file", str(config.output_file) if config.output_file else "Automatic")
    elif config.mode is Mode.CHUNK:
        table.add_row("Chunk size", fmt_size(config.chunk_size or 0))
        table.add_row("Chunk prefix", config.output_prefix)
        table.add_row("Follow symlinks", "Yes" if config.follow_symlinks else "No")

    console.print()
    console.print(table)
    console.print()

    # ── Confirm ────────────────────────────────────────────────────
    proceed = _confirm_prompt("Start processing?", default=True)
    if not proceed:
        console.print("[yellow]Operation cancelled.[/yellow]")
        raise typer.Exit(0)

    return config
