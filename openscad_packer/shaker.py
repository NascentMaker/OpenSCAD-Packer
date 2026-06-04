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
    pool: dict[str, FunctionDeclaration | ModuleDeclaration],
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
            called = collect_called_names([pool[name]])
            for callee in called:
                if callee in pool and callee not in reachable:
                    next_frontier.add(callee)
        frontier = next_frontier

    return reachable
