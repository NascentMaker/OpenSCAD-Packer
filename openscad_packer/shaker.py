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

import dataclasses

from openscad_parser.ast.nodes import (
    ASTNode,
    FunctionDeclaration,
    Identifier,
    ModularCall,
    ModuleDeclaration,
    PrimaryCall,
)


def collect_called_names(nodes: list[ASTNode]) -> set[str]:
    """Walk AST nodes and collect all function/module names that are called."""
    found: set[str] = set()
    for node in nodes:
        _walk_node(node, found)
    return found


def _walk_node(node: object, found: set[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_node(item, found)
        return
    if not isinstance(node, ASTNode):
        return

    if isinstance(node, ModularCall):
        found.add(node.name.name)
    elif isinstance(node, PrimaryCall) and isinstance(node.left, Identifier):
        found.add(node.left.name)

    for f in dataclasses.fields(node):
        if f.name in ("position", "scope"):
            continue
        _walk_node(getattr(node, f.name), found)


def compute_reachable(
    seed_names: set[str],
    pool: dict[str, list[FunctionDeclaration | ModuleDeclaration]],
) -> set[str]:
    """Fixed-point reachability from seed_names through the definition pool.

    Handles mutual recursion (A calls B, B calls A) via frontier/visited tracking.
    """
    reachable: set[str] = set()
    frontier = seed_names & pool.keys()

    while frontier:
        reachable |= frontier
        next_frontier: set[str] = set()
        for name in frontier:
            called = collect_called_names(pool[name])
            for callee in called:
                if callee in pool and callee not in reachable:
                    next_frontier.add(callee)
        frontier = next_frontier

    return reachable
