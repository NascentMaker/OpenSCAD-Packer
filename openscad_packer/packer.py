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

import contextlib
import io
import os
import sys

from openscad_parser.ast import getASTfromFile, getASTfromString
from openscad_parser.ast.nodes import (
    ASTNode,
    Assignment,
    CommentLine,
    CommentSpan,
    FunctionDeclaration,
    IncludeStatement,
    ModuleDeclaration,
    UseStatement,
)
from openscad_parser.ast.pretty_print import to_openscad

from .resolver import resolve_library
from .shaker import collect_called_names, compute_reachable


def _strip_expression_comments(code: str) -> str:
    """Strip `//` line comments that appear inside `()` or `[]` expression contexts.

    Statement-level comments (including OpenSCAD Customizer magic annotations like
    `// [min:max]` and section headers like `/* [Name] */`) are left untouched.
    `/* */` block comments are always preserved regardless of nesting depth.
    """
    result: list[str] = []
    i = 0
    depth = 0  # nesting inside ( and [ only; { is a scope, not an expression

    while i < len(code):
        c = code[i]

        # String literal — skip its contents verbatim
        if c == '"':
            result.append(c)
            i += 1
            while i < len(code):
                c = code[i]
                result.append(c)
                if c == '\\':
                    i += 1
                    if i < len(code):
                        result.append(code[i])
                elif c == '"':
                    break
                i += 1
            i += 1
            continue

        # Block comment — always preserve
        if c == '/' and i + 1 < len(code) and code[i + 1] == '*':
            result.append(c)
            i += 1
            result.append(code[i])
            i += 1
            while i < len(code):
                if code[i] == '*' and i + 1 < len(code) and code[i + 1] == '/':
                    result.append(code[i])
                    result.append(code[i + 1])
                    i += 2
                    break
                result.append(code[i])
                i += 1
            continue

        # Line comment
        if c == '/' and i + 1 < len(code) and code[i + 1] == '/':
            if depth > 0:
                # Inside an expression — strip to end of line (keep the newline)
                while i < len(code) and code[i] != '\n':
                    i += 1
            else:
                # Statement level — preserve
                result.append(c)
                i += 1
            continue

        # Track expression depth for ( and [ only
        if c in '([':
            depth += 1
        elif c in ')]':
            depth = max(0, depth - 1)

        result.append(c)
        i += 1

    return ''.join(result)


def _merge_inline_comments(raw: str, body_nodes: list[ASTNode]) -> str:
    """Merge CommentLine nodes that were trailing on the same source line as the
    preceding statement back onto that line.

    The parser emits `var = val; // [min:max]` as two separate nodes (Assignment +
    CommentLine) even though they shared one source line.  to_openscad() renders them
    on consecutive lines.  This post-processor detects those pairs via position.line
    equality, then merges the comment into the preceding output line.

    A multiset (Counter) of comment texts is used so duplicate annotation texts
    (e.g. two variables both annotated `// [0:100]`) are each matched at most once.
    """
    from collections import Counter

    # Pre-scan: collect comment texts that must be merged, preserving multiplicity.
    inline_texts: Counter[str] = Counter()
    prev: ASTNode | None = None
    for node in body_nodes:
        if (
            isinstance(node, CommentLine)
            and prev is not None
            and not isinstance(prev, (CommentLine, CommentSpan))
        ):
            node_line = getattr(getattr(node, "position", None), "line", None)
            prev_line = getattr(getattr(prev, "position", None), "line", None)
            if node_line is not None and node_line == prev_line:
                inline_texts[node.text] += 1
        prev = node

    if not inline_texts:
        return raw

    remaining = Counter(inline_texts)
    result: list[str] = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if (
            stripped.startswith("//")
            and result
            and result[-1].rstrip().endswith(";")
        ):
            comment_text = stripped[2:]  # text after the `//`
            if remaining.get(comment_text, 0) > 0:
                result[-1] = result[-1].rstrip() + f" //{comment_text}"
                remaining[comment_text] -= 1
                continue
        result.append(line)

    return "\n".join(result)


class PackerError(Exception):
    pass


class Packer:
    """Packs an OpenSCAD entry file and all its dependencies into one file."""

    def __init__(
        self,
        entry_file: str,
        library_paths: list[str],
        preserve_comments: bool = True,
    ) -> None:
        self.entry_file = os.path.abspath(entry_file)
        self.library_paths = [os.path.abspath(p) for p in library_paths]
        self.preserve_comments = preserve_comments

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
        nodes = self._parse_entry_file()
        self._process_file_nodes(nodes, self.entry_file)

        seed = collect_called_names(self._body_nodes)
        reachable = compute_reachable(seed, self._pool)
        used_defs = [
            defn
            for n in self._pool_order
            if n in reachable
            for defn in self._pool[n]
        ]

        # Put assignments/comments before library defs so Customizer sees them at
        # the top of the file; leave geometry calls (module calls etc.) after defs.
        # OpenSCAD's declarative semantics mean order doesn't affect rendering.
        _is_header = (Assignment, CommentLine, CommentSpan)
        header_nodes = [n for n in self._body_nodes if isinstance(n, _is_header)]
        footer_nodes = [n for n in self._body_nodes if not isinstance(n, _is_header)]

        raw = to_openscad(header_nodes + used_defs + footer_nodes)
        return _merge_inline_comments(raw, self._body_nodes)

    def _parse_entry_file(self) -> list[ASTNode]:
        if not self.preserve_comments:
            return getASTfromFile(self.entry_file, process_includes=False) or []

        # Pre-process: strip `//` comments inside expressions so that statement-level
        # magic comments (e.g. `// [0:100]`, `/* [Section] */`) survive the parse.
        with open(self.entry_file, encoding="utf-8") as fh:
            source = fh.read()
        safe_source = _strip_expression_comments(source)

        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            nodes = getASTfromString(
                safe_source,
                include_comments=True,
                origin=self.entry_file,
            )

        if nodes is not None:
            return nodes

        # Fallback: the pre-processed source still couldn't be parsed with comments.
        nodes = getASTfromFile(self.entry_file, process_includes=False) or []
        if nodes:
            print(
                "Warning: comments could not be preserved; packing without comments. "
                "Pass --no-preserve-comments to suppress this warning.",
                file=sys.stderr,
            )
        return nodes

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
