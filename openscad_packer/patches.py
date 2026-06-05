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

"""Workarounds for two upstream openscad-parser bugs.

These patches are applied once at import time by monkey-patching the affected
classes.  Both bugs have upstream PRs filed.

Bug 1 — Empty-string literals rendered as ``"" | ""``
------------------------------------------------------
Root cause: Arpeggio's ``RegExMatch._parse`` uses ``if matched:`` to decide
whether to return a Terminal node.  An empty-string regex match sets
``matched = ''``, which is falsy, so the Terminal is **not** returned.  The
``string_contents`` rule (which wraps the regex) therefore produces no child
node for empty strings, leaving ``visit_string_literal`` with ``children=[]``.
The fallback branch calls ``str(node.value)``, and ``NonTerminal.value``
calls ``NonTerminal.__str__``, which joins its children (the two ``"``
Terminals) with `` | `` — producing ``'" | "'``.  ``StringLiteral.__str__``
then wraps that in quotes, giving ``"" | ""``.

Fix: when ``children`` is empty inside ``visit_string_literal``, return
``StringLiteral(val="")`` directly instead of falling back to
``str(node.value)``.

Bug 2 — Two-argument ranges rendered with wrong step order
----------------------------------------------------------
Root cause: ``RangeLiteral.__str__`` emits ``[start:end:step]``.  For a
three-argument source range ``[s:p:e]`` (OpenSCAD syntax: start : step : end)
the builder stores ``end=p`` and ``step=e``, so the output ``[s:p:e]`` is
accidentally correct.  But for a *two*-argument range ``[s:e]``, the builder
synthesises a default ``step=NumberLiteral(1.0)`` tagged with the **range
node's own position**, then stores it in the ``step`` field.  The output
``[s:e:1]`` is read by OpenSCAD as start=s, step=e, end=1 — wrong semantics.

Fix: inside ``RangeLiteral.__str__``, detect the synthesised default by
comparing ``self.step.position == self.position`` (both were created from the
same Arpeggio node position).  When they match, emit ``[start:end]``; when
they differ (explicit three-argument range), emit ``[start:end:step]`` as
before (the internal field swap is still present but cancels out).
"""
from __future__ import annotations

from openscad_parser.ast.builder import ASTBuilderVisitor
from openscad_parser.ast.nodes import RangeLiteral, StringLiteral


def _patch_empty_string() -> None:
    _orig = ASTBuilderVisitor.visit_string_literal

    def visit_string_literal(self, node, children):  # type: ignore[override]
        if not children:
            # Arpeggio dropped the zero-length string_contents Terminal because
            # RegExMatch._parse uses ``if matched:`` (falsy for '').  Return an
            # empty string rather than falling back to str(node.value), which
            # produces the broken Arpeggio ' | '-joined representation.
            return StringLiteral(val="", position=self._get_node_position(node))
        return _orig(self, node, children)

    ASTBuilderVisitor.visit_string_literal = visit_string_literal


def _patch_range_str() -> None:
    def __str__(self: RangeLiteral) -> str:  # type: ignore[override]
        # A synthesised default step (for 2-arg ranges) is given the range
        # node's own position by visit_range_expr.  An explicit third argument
        # has its own distinct source position.  Use this to tell them apart.
        if self.step.position == self.position:
            return f"[{self.start}:{self.end}]"
        return f"[{self.start}:{self.end}:{self.step}]"

    RangeLiteral.__str__ = __str__


_patch_empty_string()
_patch_range_str()
