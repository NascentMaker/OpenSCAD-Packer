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

import os

from openscad_parser.ast import findLibraryFile


def resolve_library(
    curr_file: str,
    lib_path: str,
    extra_paths: list[str],
) -> str | None:
    """Resolve lib_path to an absolute file path.

    Search order:
      1. extra_paths directories (checked in order)
      2. findLibraryFile standard OpenSCAD rules:
         same dir as curr_file → OPENSCADPATH env → platform default
    """
    for base in extra_paths:
        candidate = os.path.join(base, lib_path)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return findLibraryFile(curr_file, lib_path)
