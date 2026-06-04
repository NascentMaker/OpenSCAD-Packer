# Copyright (C) 2026  Torgny Bjers
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://gnu.org>.

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
