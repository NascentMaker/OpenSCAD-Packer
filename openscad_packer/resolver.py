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
