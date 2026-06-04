from __future__ import annotations

from pathlib import Path

import click

from .packer import Packer, PackerError


@click.group()
def cli() -> None:
    """OpenSCAD Packer — bundle a .scad file and all its dependencies."""


@cli.command()
@click.argument("input", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, writable=True),
    default=None,
    help="Output file path. Defaults to stdout.",
)
@click.option(
    "-L",
    "--library-path",
    "library_paths",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, readable=True),
    help="Extra library search path (may be repeated).",
)
def pack(input: str, output: str | None, library_paths: tuple[str, ...]) -> None:
    """Pack INPUT into a single self-contained OpenSCAD file."""
    try:
        result = Packer(input, list(library_paths)).pack()
    except PackerError as exc:
        raise click.ClickException(str(exc)) from exc

    if output is None:
        click.echo(result, nl=False)
    else:
        Path(output).write_text(result, encoding="utf-8")
        click.echo(f"Written to {output}", err=True)
