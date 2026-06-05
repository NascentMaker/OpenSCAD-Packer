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

from openscad_parser.ast import getASTfromFile
from openscad_parser.ast.nodes import (
    ASTNode,
    FunctionDeclaration,
    IncludeStatement,
    ModuleDeclaration,
    UseStatement,
)
from openscad_parser.ast.pretty_print import to_openscad

from .resolver import resolve_library
from .shaker import collect_called_names, compute_reachable


class PackerError(Exception):
    pass


class Packer:
    """Packs an OpenSCAD entry file and all its dependencies into one file."""

    def __init__(self, entry_file: str, library_paths: list[str]) -> None:
        self.entry_file = os.path.abspath(entry_file)
        self.library_paths = [os.path.abspath(p) for p in library_paths]

        # Definition pool: name → list of nodes, insertion-ordered via _pool_order.
        # A name may have both a FunctionDeclaration and a ModuleDeclaration (OpenSCAD
        # dual-namespace pattern used by BOSL). Last-writer-wins per type; first-encounter
        # order preserved across names.
        self._pool: dict[str, list[FunctionDeclaration | ModuleDeclaration]] = {}
        self._pool_order: list[str] = []

        # Non-definition top-level nodes (assignments, module calls, etc.)
        self._body_nodes: list[ASTNode] = []

        # Absolute paths of already-visited include files (cycle detection)
        self._visited_includes: set[str] = set()

    def pack(self) -> str:
        """Run both phases and return pretty-printed packed source."""
        nodes = getASTfromFile(self.entry_file, process_includes=False) or []
        self._process_file_nodes(nodes, self.entry_file)

        seed = collect_called_names(self._body_nodes)
        reachable = compute_reachable(seed, self._pool)
        used_defs = [
            defn
            for n in self._pool_order
            if n in reachable
            for defn in self._pool[n]
        ]

        return to_openscad(used_defs + self._body_nodes)

    # ------------------------------------------------------------------
    # Phase 1: collect
    # ------------------------------------------------------------------

    def _process_file_nodes(self, nodes: list[ASTNode], curr_file: str) -> None:
        for node in nodes:
            if isinstance(node, UseStatement):
                self._handle_use(node, curr_file)
            elif isinstance(node, IncludeStatement):
                self._handle_include(node, curr_file)
            elif isinstance(node, (FunctionDeclaration, ModuleDeclaration)):
                self._add_to_pool(node)
            else:
                self._body_nodes.append(node)

    def _handle_use(self, stmt: UseStatement, curr_file: str) -> None:
        lib_path = stmt.filepath.val
        resolved = resolve_library(curr_file, lib_path, self.library_paths)
        if resolved is None:
            raise PackerError(
                f"Cannot resolve library '{lib_path}' (used from '{curr_file}'). "
                f"Install the library or pass its directory with -L."
            )

        # process_includes=True: let the parser flatten the library's own includes
        lib_nodes = getASTfromFile(resolved, process_includes=True) or []
        for node in lib_nodes:
            if isinstance(node, (FunctionDeclaration, ModuleDeclaration)):
                self._add_to_pool(node)
            # Variables and top-level calls from used files are discarded

    def _handle_include(self, stmt: IncludeStatement, curr_file: str) -> None:
        lib_path = stmt.filepath.val
        resolved = resolve_library(curr_file, lib_path, self.library_paths)
        if resolved is None:
            raise PackerError(
                f"Cannot resolve include '{lib_path}' (included from '{curr_file}'). "
                f"Install the library or pass its directory with -L."
            )

        abs_path = os.path.abspath(resolved)
        if abs_path in self._visited_includes:
            return  # cycle — silently skip
        self._visited_includes.add(abs_path)

        inc_nodes = getASTfromFile(abs_path, process_includes=False) or []
        self._process_file_nodes(inc_nodes, abs_path)

    def _add_to_pool(self, node: FunctionDeclaration | ModuleDeclaration) -> None:
        name = node.name.name
        if name not in self._pool:
            self._pool_order.append(name)
            self._pool[name] = []
        for i, existing in enumerate(self._pool[name]):
            if type(existing) is type(node):
                self._pool[name][i] = node
                return
        self._pool[name].append(node)
