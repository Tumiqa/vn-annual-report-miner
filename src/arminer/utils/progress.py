# -*- coding: utf-8 -*-
"""
arminer.utils.progress
========================
Rich progress bars và UI helpers.
"""

from __future__ import annotations

from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn,
    TimeElapsedColumn, TimeRemainingColumn, MofNCompleteColumn,
)


console = Console()


def create_progress() -> Progress:
    """Tạo progress bar chuẩn cho pipeline."""
    return Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
    )


def print_header(title: str, subtitle: str = "") -> None:
    """In header đẹp."""
    from rich.panel import Panel
    content = f"[bold]{title}[/]"
    if subtitle:
        content += f"\n[dim]{subtitle}[/]"
    console.print(Panel.fit(content, border_style="cyan"))


def print_success(message: str) -> None:
    console.print(f"[bold green][OK] {message}[/]")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow][WARN] {message}[/]")


def print_error(message: str) -> None:
    console.print(f"[bold red][ERR] {message}[/]")


def print_step(step: int, total: int, message: str) -> None:
    console.print(f"[cyan]({step}/{total})[/] {message}")
