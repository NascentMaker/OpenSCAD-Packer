"""Regression tests for workarounds to upstream openscad-parser bugs.

These tests verify that openscad_packer.patches correctly fixes two
round-trip bugs present in the openscad-parser package.  See the docstring
in openscad_packer/patches.py for full root-cause analysis.

Coverage areas
--------------
* Bug 1 (empty-string literal) — empty "" round-trips cleanly, not as "" | ""
* Bug 2 (two-argument range)   — [s:e] round-trips as [s:e], not [s:e:1]
* Integration                  — BOSL-style patterns that triggered both bugs
"""
from __future__ import annotations

from pathlib import Path

import pytest

import openscad_packer  # ensure patches are applied
from openscad_parser.ast import getASTfromFile
from openscad_parser.ast.pretty_print import to_openscad

from openscad_packer.packer import Packer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_and_print(path: Path, src: str) -> str:
    """Write *src* to *path*, parse it, and pretty-print back to string."""
    path.write_text(src, encoding="utf-8")
    nodes = getASTfromFile(str(path), process_includes=False) or []
    return to_openscad(nodes)


def pack(entry: Path, library_paths: list[str] | None = None) -> str:
    return Packer(str(entry), library_paths or []).pack()


def write(directory: Path, name: str, content: str) -> Path:
    f = directory / name
    f.write_text(content, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Bug 1: empty-string literals
# ---------------------------------------------------------------------------

class TestEmptyStringLiteral:
    """Empty string "" must round-trip as "" not "" | ""."""

    def test_empty_string_assignment(self, tmp_path):
        out = parse_and_print(tmp_path / "t.scad", 'x = "";')
        assert '""' in out
        assert '"" | ""' not in out

    def test_empty_string_equality(self, tmp_path):
        src = 'function is_empty(v) = v == "";'
        out = parse_and_print(tmp_path / "t.scad", src)
        assert '"" | ""' not in out
        assert 'v ==' in out
        assert '""' in out

    def test_empty_string_in_logical_or(self, tmp_path):
        # Mimics BOSL compat.scad is_str pattern:
        # function is_str(v) = v=="" || v[0]!=undef;
        src = 'function is_str(v) = v=="" || v[0]!=undef;'
        out = parse_and_print(tmp_path / "t.scad", src)
        assert '"" | ""' not in out
        assert '""' in out
        assert '||' in out

    def test_empty_string_in_ternary(self, tmp_path):
        src = 'x = (v=="") ? "yes" : "no";'
        out = parse_and_print(tmp_path / "t.scad", src)
        assert '"" | ""' not in out

    def test_multiple_empty_strings(self, tmp_path):
        src = 'x = (a=="" && b=="") ? 1 : 0;'
        out = parse_and_print(tmp_path / "t.scad", src)
        assert '"" | ""' not in out
        # Both empty strings should appear
        assert out.count('""') >= 2

    def test_non_empty_string_unaffected(self, tmp_path):
        src = 'x = "hello";'
        out = parse_and_print(tmp_path / "t.scad", src)
        assert '"hello"' in out

    def test_empty_string_round_trip_via_packer(self, tmp_path):
        lib = write(tmp_path, "lib.scad", 'function isempty(v) = v == "";')
        entry = write(tmp_path, "entry.scad", 'use <lib.scad>\ny = isempty("test");')
        result = pack(entry)
        assert '"" | ""' not in result
        assert '""' in result
        assert 'isempty' in result


# ---------------------------------------------------------------------------
# Bug 2: two-argument range literals
# ---------------------------------------------------------------------------

class TestRangeLiteral:
    """Two-arg ranges [s:e] must round-trip as [s:e], not [s:e:1]."""

    def test_two_arg_range_integer(self, tmp_path):
        src = "x = [for (i=[0:2]) i];"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[0:2]" in out
        assert "[0:2:1]" not in out

    def test_two_arg_range_variable(self, tmp_path):
        src = "x = [for (i=[0:len(v)-1]) v[i]];"
        out = parse_and_print(tmp_path / "t.scad", src)
        # The key symptom was [0:len(v1) - 1:1] — the :1 should not appear
        assert ":1]" not in out

    def test_two_arg_range_negative(self, tmp_path):
        src = "x = [for (i=[-3:3]) i];"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[-3:3]" in out
        assert "[-3:3:1]" not in out

    def test_three_arg_range_explicit_step_preserved(self, tmp_path):
        # [0:1:2] in OpenSCAD means start=0, step=1, end=2
        src = "x = [for (i=[0:1:2]) i];"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[0:1:2]" in out

    def test_three_arg_range_large_step_preserved(self, tmp_path):
        # [0:5:1] means start=0, step=5, end=1 — semantically different from [0:5]
        src = "x = [for (i=[0:5:1]) i];"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[0:5:1]" in out
        assert "[0:5]" not in out

    def test_three_arg_range_negative_step_preserved(self, tmp_path):
        # [10:0:-1] means start=10, step=0, end=-1 in internal storage
        src = "x = [for (i=[10:-1:0]) i];"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[10:-1:0]" in out

    def test_three_arg_range_float_step_preserved(self, tmp_path):
        src = "x = [for (i=[0:0.5:2]) i];"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[0:0.5:2]" in out

    def test_two_arg_range_in_for_loop_module(self, tmp_path):
        src = "module m() { for (i=[0:3]) { cube(i); } }"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[0:3]" in out
        assert "[0:3:1]" not in out

    def test_two_arg_range_round_trip_via_packer(self, tmp_path):
        lib = write(tmp_path, "lib.scad",
                    "function vsum(v) = [for (i=[0:len(v)-1]) v[i]];")
        entry = write(tmp_path, "entry.scad",
                      "use <lib.scad>\nx = vsum([1,2,3]);")
        result = pack(entry)
        # Should not have the broken :1] suffix on the 2-arg range
        assert ":1]" not in result
        assert "vsum" in result


# ---------------------------------------------------------------------------
# Integration: BOSL-style patterns
# ---------------------------------------------------------------------------

class TestBOSLPatterns:
    """Patterns drawn from revarbat/BOSL that triggered both bugs."""

    def test_is_str_pattern(self, tmp_path):
        # Mimics BOSL compat.scad is_str — uses v=="" and || together
        src = (
            'function is_str(v) = '
            '(version_num() > 20190100) ? is_string(v) : '
            '(v=="" || (v[0]!=undef));'
        )
        out = parse_and_print(tmp_path / "t.scad", src)
        assert '"" | ""' not in out
        assert '""' in out
        assert '||' in out

    def test_vmul_pattern(self, tmp_path):
        # Mimics BOSL math.scad vmul — uses 2-arg range [0:len(v1)-1]
        src = "function vmul(v1, v2) = [for (i=[0:len(v1)-1]) v1[i]*v2[i]];"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[0:len(v1) - 1]" in out
        assert ":1]" not in out

    def test_point2d_pattern(self, tmp_path):
        # Mimics BOSL math.scad point2d — uses 2-arg range [0:1]
        src = "function point2d(p) = [for (i=[0:1]) p[i]==undef ? 0 : p[i]];"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[0:1]" in out
        assert "[0:1:1]" not in out

    def test_point3d_pattern(self, tmp_path):
        # Mimics BOSL math.scad point3d — uses 2-arg range [0:2]
        src = "function point3d(p) = [for (i=[0:2]) p[i]==undef ? 0 : p[i]];"
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[0:2]" in out
        assert "[0:2:1]" not in out

    def test_scalar_vec3_pattern(self, tmp_path):
        # Mimics BOSL compat.scad scalar_vec3 — both bugs potentially triggered
        src = (
            "function default(v, dflt) = v==undef ? dflt : v;\n"
            "function scalar_vec3(v, dflt) =\n"
            "  !is_def(v) ? undef :\n"
            "  is_array(v) ? [for (i=[0:2]) default(v[i], default(dflt, 0))] :\n"
            "  is_def(dflt) ? [v,dflt,dflt] : [v,v,v];\n"
        )
        out = parse_and_print(tmp_path / "t.scad", src)
        assert "[0:2]" in out
        assert "[0:2:1]" not in out

    def test_bosl_compat_mini_via_packer(self, tmp_path):
        """Packs a mini BOSL compat subset and verifies no corruption."""
        compat = write(tmp_path, "compat.scad", """\
function is_def(v) = v != undef;
function is_str(v) = v=="" || (is_def(v) && is_def(v[0]));
function vmul(v1, v2) = [for (i=[0:len(v1)-1]) v1[i]*v2[i]];
function point3d(p) = [for (i=[0:2]) p[i]==undef ? 0 : p[i]];
""")
        entry = write(tmp_path, "entry.scad", """\
use <compat.scad>
a = vmul([1,2,3],[4,5,6]);
b = point3d([1,2]);
c = is_str("hello");
""")
        result = pack(entry)
        assert '"" | ""' not in result
        assert ":1]" not in result
        assert "vmul" in result
        assert "point3d" in result
        assert "is_str" in result
