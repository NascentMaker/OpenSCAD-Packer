"""Integration tests for openscad_packer.packer."""
from pathlib import Path

import sys

import pytest

from openscad_packer.packer import Packer, PackerError, _strip_expression_comments


def write(directory: Path, name: str, content: str) -> Path:
    f = directory / name
    f.write_text(content)
    return f


def pack(entry: Path, library_paths: list[str] | None = None) -> str:
    return Packer(str(entry), library_paths or []).pack()


# ---------------------------------------------------------------------------
# use <lib> semantics
# ---------------------------------------------------------------------------

class TestUseStatement:
    def test_used_function_is_included(self, tmp_path):
        write(tmp_path, "lib.scad", "function foo(x) = x * 2;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(5);")
        assert "foo" in pack(entry)

    def test_unused_function_from_use_is_dropped(self, tmp_path):
        write(tmp_path, "lib.scad", "function used(x) = x; function unused(x) = 99;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = used(1);")
        result = pack(entry)
        assert "used" in result
        assert "unused" not in result

    def test_variables_from_use_are_discarded(self, tmp_path):
        write(tmp_path, "lib.scad", "x = 42; function foo(n) = n;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(1);")
        result = pack(entry)
        assert "x = 42" not in result
        assert "foo" in result

    def test_top_level_calls_from_use_are_discarded(self, tmp_path):
        write(tmp_path, "lib.scad", "cube(99); function foo(n) = n;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(1);")
        result = pack(entry)
        assert "cube(99)" not in result

    def test_use_raises_on_missing_library(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "use <nonexistent.scad>\ncube(10);")
        with pytest.raises(PackerError, match="nonexistent.scad"):
            pack(entry)

    def test_use_error_message_names_the_file(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "use <missing_lib.scad>\ncube(10);")
        with pytest.raises(PackerError, match="missing_lib.scad"):
            pack(entry)

    def test_use_with_extra_library_path(self, tmp_path):
        lib_dir = tmp_path / "libs"
        lib_dir.mkdir()
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        write(lib_dir, "mylib.scad", "function triple(x) = x * 3;")
        entry = write(proj_dir, "entry.scad", "use <mylib.scad>\ny = triple(4);")
        result = Packer(str(entry), [str(lib_dir)]).pack()
        assert "triple" in result
        assert "y = triple(4)" in result

    def test_use_module_is_tree_shaked(self, tmp_path):
        write(tmp_path, "lib.scad",
              "module used_mod(s) { cube(s); } module unused_mod() { sphere(1); }")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\nused_mod(5);")
        result = pack(entry)
        assert "used_mod" in result
        assert "unused_mod" not in result

    def test_use_no_symbols_needed_produces_no_defs(self, tmp_path):
        write(tmp_path, "lib.scad", "function foo(x) = x;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ncube(10);")
        result = pack(entry)
        assert "foo" not in result
        assert "cube" in result


# ---------------------------------------------------------------------------
# include <file> semantics
# ---------------------------------------------------------------------------

class TestIncludeStatement:
    def test_included_function_is_tree_shaked(self, tmp_path):
        write(tmp_path, "helpers.scad",
              "function used(x) = x * 2; function unused(x) = x + 99;")
        entry = write(tmp_path, "entry.scad",
                      "include <helpers.scad>\ny = used(5);")
        result = pack(entry)
        assert "used" in result
        assert "unused" not in result

    def test_included_assignment_is_always_kept(self, tmp_path):
        write(tmp_path, "helpers.scad", "x = 42; function foo(n) = n;")
        entry = write(tmp_path, "entry.scad", "include <helpers.scad>\ny = foo(x);")
        result = pack(entry)
        assert "x = 42" in result

    def test_included_top_level_module_call_is_always_kept(self, tmp_path):
        write(tmp_path, "helpers.scad", "cube(10);")
        entry = write(tmp_path, "entry.scad", "include <helpers.scad>")
        result = pack(entry)
        assert "cube" in result

    def test_include_raises_on_missing_file(self, tmp_path):
        entry = write(tmp_path, "entry.scad",
                      "include <nonexistent.scad>\ncube(1);")
        with pytest.raises(PackerError, match="nonexistent.scad"):
            pack(entry)

    def test_include_raises_error_message_names_file(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "include <missing_helper.scad>")
        with pytest.raises(PackerError, match="missing_helper.scad"):
            pack(entry)

    def test_include_cycle_does_not_loop(self, tmp_path):
        write(tmp_path, "a.scad", "include <b.scad>\nfunction fa(x) = x;")
        write(tmp_path, "b.scad", "include <a.scad>\nfunction fb(x) = x;")
        entry = write(tmp_path, "entry.scad", "include <a.scad>\nfa(1);")
        result = pack(entry)
        assert result is not None

    def test_include_nested_use_is_processed(self, tmp_path):
        write(tmp_path, "lib.scad", "function helper(x) = x * 3;")
        write(tmp_path, "middle.scad", "use <lib.scad>\nfunction wrap(x) = helper(x);")
        entry = write(tmp_path, "entry.scad",
                      "include <middle.scad>\ny = wrap(5);")
        result = pack(entry)
        assert "helper" in result
        assert "wrap" in result

    def test_include_with_extra_library_path(self, tmp_path):
        inc_dir = tmp_path / "includes"
        inc_dir.mkdir()
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        write(inc_dir, "shared.scad", "function sq(x) = x * x;")
        entry = write(proj_dir, "entry.scad",
                      "include <shared.scad>\ny = sq(4);")
        result = Packer(str(entry), [str(inc_dir)]).pack()
        assert "sq" in result


# ---------------------------------------------------------------------------
# Tree-shaking behaviour
# ---------------------------------------------------------------------------

class TestTreeShaking:
    def test_transitive_function_deps_included(self, tmp_path):
        write(tmp_path, "lib.scad",
              "function a(x) = b(x); function b(x) = x * 2; function unused(x) = 99;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\nresult = a(5);")
        result = pack(entry)
        assert "function a" in result
        assert "function b" in result
        assert "unused" not in result

    def test_transitive_module_deps_included(self, tmp_path):
        write(tmp_path, "lib.scad",
              "module outer(s) { inner(s); } "
              "module inner(s) { cube(s); } "
              "module unused() { sphere(1); }")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\nouter(10);")
        result = pack(entry)
        assert "outer" in result
        assert "inner" in result
        assert "unused" not in result

    def test_mutual_recursion_both_included(self, tmp_path):
        write(tmp_path, "lib.scad",
              "function is_even(n) = n == 0 ? true : is_odd(n - 1); "
              "function is_odd(n) = n == 0 ? false : is_even(n - 1);")
        entry = write(tmp_path, "entry.scad",
                      "use <lib.scad>\nresult = is_even(4);")
        result = pack(entry)
        assert "is_even" in result
        assert "is_odd" in result

    def test_entry_own_unused_function_dropped(self, tmp_path):
        entry = write(tmp_path, "entry.scad",
                      "function used(x) = x * 2;\n"
                      "function unused(x) = x + 99;\n"
                      "y = used(5);")
        result = pack(entry)
        assert "used" in result
        assert "unused" not in result

    def test_entry_own_unused_module_dropped(self, tmp_path):
        entry = write(tmp_path, "entry.scad",
                      "module box(s) { cube(s); }\n"
                      "module unused_shape() { sphere(1); }\n"
                      "box(10);")
        result = pack(entry)
        assert "box" in result
        assert "unused_shape" not in result

    def test_cross_library_transitive_dep(self, tmp_path):
        write(tmp_path, "math.scad", "function scale_val(x) = x * 1.5;")
        write(tmp_path, "shapes.scad",
              "use <math.scad>\n"
              "module scaled_box(s) { cube(scale_val(s)); }")
        entry = write(tmp_path, "entry.scad",
                      "use <shapes.scad>\nscaled_box(5);")
        # Note: use <math.scad> inside shapes.scad is processed with process_includes=True,
        # so scale_val ends up in the pool via shapes.scad's flattened parse
        result = pack(entry)
        assert "scaled_box" in result


# ---------------------------------------------------------------------------
# Output correctness
# ---------------------------------------------------------------------------

class TestOutputCorrectness:
    def test_output_contains_entry_body_nodes(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "cube(10);\nsphere(5);")
        result = pack(entry)
        assert "cube" in result
        assert "sphere" in result

    def test_assignments_appear_before_library_definitions(self, tmp_path):
        # Parametric assignments go before library defs so Customizer picks them up.
        write(tmp_path, "lib.scad", "function foo(x) = x;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(1);")
        result = pack(entry)
        assign_pos = result.index("y = foo")
        func_pos = result.index("function foo")
        assert assign_pos < func_pos

    def test_geometry_calls_appear_after_library_definitions(self, tmp_path):
        # Module calls (geometry) must come after the defs they reference.
        write(tmp_path, "lib.scad", "module box(s) { cube(s); }")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\nbox(5);")
        result = pack(entry)
        mod_pos = result.index("module box")
        call_pos = result.index("box(5)")
        assert mod_pos < call_pos

    def test_no_use_statements_in_output_for_resolved_libs(self, tmp_path):
        write(tmp_path, "lib.scad", "function foo(x) = x;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(1);")
        result = pack(entry)
        assert "use <" not in result

    def test_no_include_statements_in_output_for_resolved_files(self, tmp_path):
        write(tmp_path, "helpers.scad", "function foo(x) = x;")
        entry = write(tmp_path, "entry.scad", "include <helpers.scad>\ny = foo(1);")
        result = pack(entry)
        assert "include <" not in result

    def test_output_is_valid_string(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "cube(10);")
        result = pack(entry)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_entry_file_returns_empty_or_whitespace(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "")
        result = pack(entry)
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# Smoke tests (replicate development verification scenarios)
# ---------------------------------------------------------------------------

class TestSmoke:
    def test_full_include_chain(self, tmp_path):
        """Replicates the original smoke test from development."""
        write(tmp_path, "helpers.scad",
              "function double(x) = x * 2;\n"
              "function unused_fn(x) = x + 999;\n"
              "module unused_mod() { sphere(1); }\n"
              "module helper_box(s) { cube([s, s, s]); }\n")
        write(tmp_path, "geometry.scad",
              "include <helpers.scad>\n\n"
              "x = 42;\n\n"
              "module base_shape(size) {\n"
              "    helper_box(size);\n"
              "}\n")
        entry = write(tmp_path, "entry.scad",
                      "include <geometry.scad>\n\n"
                      "size = double(5);\n"
                      "base_shape(size);\n")
        result = pack(entry)
        assert "function double" in result
        assert "module helper_box" in result
        assert "module base_shape" in result
        assert "unused_fn" not in result
        assert "unused_mod" not in result
        assert "x = 42" in result
        assert "double(5)" in result
        assert "base_shape" in result

    def test_use_extra_library_path_smoke(self, tmp_path):
        """Replicates the -L flag smoke test from development."""
        lib_dir = tmp_path / "mylibs"
        lib_dir.mkdir()
        write(lib_dir, "extra.scad", "function triple(x) = x * 3;")
        entry = write(tmp_path, "entry.scad",
                      "use <extra.scad>\ny = triple(4);")
        result = Packer(str(entry), [str(lib_dir)]).pack()
        assert "function triple" in result
        assert "y = triple(4)" in result

    def test_mutual_recursion_smoke(self, tmp_path):
        """Replicates the mutual recursion smoke test from development."""
        write(tmp_path, "mutual.scad",
              "function is_even(n) = n == 0 ? true : is_odd(n - 1);\n"
              "function is_odd(n) = n == 0 ? false : is_even(n - 1);\n"
              "function unrelated(x) = x * 99;\n")
        entry = write(tmp_path, "entry.scad",
                      "use <mutual.scad>\nresult = is_even(4);")
        result = pack(entry)
        assert "is_even" in result
        assert "is_odd" in result
        assert "unrelated" not in result


# ---------------------------------------------------------------------------
# _strip_expression_comments unit tests
# ---------------------------------------------------------------------------

class TestStripExpressionComments:
    def test_statement_level_comment_preserved(self):
        src = "x = 10; // [0:100]\n"
        assert "// [0:100]" in _strip_expression_comments(src)

    def test_inline_expression_comment_stripped(self):
        src = "cube([10, // width\n20]);\n"
        result = _strip_expression_comments(src)
        assert "// width" not in result
        assert "cube" in result

    def test_block_comment_always_preserved(self):
        src = "/* [Parameters] */\nx = 10;\n"
        assert "/* [Parameters] */" in _strip_expression_comments(src)

    def test_block_comment_inside_expression_preserved(self):
        src = "cube(/* note */ 10);\n"
        assert "/* note */" in _strip_expression_comments(src)

    def test_string_containing_comment_marker_untouched(self):
        src = 'echo("see // this"); // real comment\n'
        result = _strip_expression_comments(src)
        assert '"see // this"' in result
        assert "// real comment" in result

    def test_nested_brackets_depth_tracked(self):
        src = "x = foo([a, // inner\n b]); // outer\n"
        result = _strip_expression_comments(src)
        assert "// inner" not in result
        assert "// outer" in result

    def test_no_comments_unchanged(self):
        src = "x = 10;\ncube(x);\n"
        assert _strip_expression_comments(src) == src

    def test_escaped_quote_inside_string_preserved(self):
        # `\"` inside a string literal must be consumed as an escape, not treated as
        # the closing quote — exercises the `c == '\\'` branch (lines 62-64).
        src = 'echo("say \\"hello\\""); // real\n'
        result = _strip_expression_comments(src)
        assert '\\"hello\\"' in result
        assert "// real" in result

    def test_unterminated_string_at_eof_handled(self):
        # A string literal that reaches EOF without a closing `"` must not crash —
        # exercises the `while i < len(code)` exit-without-break branch (58->68).
        result = _strip_expression_comments('"unclosed')
        assert '"unclosed' in result

    def test_unterminated_block_comment_at_eof_handled(self):
        # A block comment that reaches EOF without `*/` must not crash —
        # exercises the `while i < len(code)` exit-without-break branch (77->85).
        result = _strip_expression_comments("/* unclosed")
        assert "/* unclosed" in result


# ---------------------------------------------------------------------------
# Comment preservation
# ---------------------------------------------------------------------------

class TestCommentPreservation:
    def test_line_comment_preserved_by_default(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "// A line comment\ncube(10);")
        result = pack(entry)
        assert "// A line comment" in result

    def test_block_comment_preserved_by_default(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "/* A block comment */\ncube(10);")
        result = pack(entry)
        assert "A block comment" in result

    def test_magic_comment_range_inline_on_same_line(self, tmp_path):
        # `// [1:100]` trailing a variable must appear on the same line for Customizer.
        entry = write(tmp_path, "entry.scad", "width = 20; // [1:100]\ncube(width);")
        result = pack(entry)
        assert "width = 20; // [1:100]" in result

    def test_magic_comment_standalone_on_next_line_preserved(self, tmp_path):
        # A standalone `// [min:max]` on its own line should stay on its own line.
        entry = write(tmp_path, "entry.scad", "width = 20;\n// [1:100]\ncube(width);")
        result = pack(entry)
        assert "[1:100]" in result

    def test_magic_comment_section_header_preserved(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "/* [Parameters] */\nwidth = 20;\ncube(width);")
        result = pack(entry)
        assert "[Parameters]" in result

    def test_description_comment_not_merged_with_following_assignment(self, tmp_path):
        # A description comment on the line BEFORE the assignment must stay standalone.
        entry = write(tmp_path, "entry.scad",
                      "// Wall thickness, in mm\n"
                      "wall_thickness = 2; // [1:10]\n"
                      "cube(wall_thickness);")
        result = pack(entry)
        assert "// Wall thickness, in mm" in result
        assert "wall_thickness = 2; // [1:10]" in result

    def test_comments_from_used_library_not_preserved(self, tmp_path):
        write(tmp_path, "lib.scad", "// Library internal comment\nfunction foo(x) = x;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(1);")
        result = pack(entry)
        assert "Library internal comment" not in result

    def test_no_preserve_comments_strips_entry_comments(self, tmp_path):
        entry = write(tmp_path, "entry.scad", "// Should be stripped\ncube(10);")
        result = Packer(str(entry), [], preserve_comments=False).pack()
        assert "Should be stripped" not in result

    def test_inline_expression_comment_stripped_no_warning(self, tmp_path, capsys):
        # Comments inside expressions are pre-stripped before parse, so no warning is emitted
        # and the output is still correct.
        entry = write(tmp_path, "entry.scad",
                      "cube([\n"
                      "    10, // width\n"
                      "    20  // height\n"
                      "]);")
        result = pack(entry)
        assert "cube" in result
        captured = capsys.readouterr()
        assert "warning" not in captured.err.lower()

    def test_fallback_warning_when_string_parse_fails(self, tmp_path, capsys, monkeypatch):
        entry = write(tmp_path, "entry.scad", "// A comment\ncube(10);")
        monkeypatch.setattr(sys.modules[Packer.__module__], "getASTfromString", lambda *a, **kw: None)
        result = Packer(str(entry), []).pack()
        assert "cube" in result
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower()

    def test_fallback_no_warning_for_empty_file(self, tmp_path, capsys, monkeypatch):
        # When getASTfromString fails AND the file is empty, the fallback also returns
        # nothing — `if nodes:` is False so no warning is printed (branch 239->245).
        entry = write(tmp_path, "entry.scad", "")
        monkeypatch.setattr(sys.modules[Packer.__module__], "getASTfromString", lambda *a, **kw: None)
        result = Packer(str(entry), []).pack()
        assert result.strip() == ""
        captured = capsys.readouterr()
        assert "warning" not in captured.err.lower()

    def test_standalone_comment_after_semicolon_not_merged(self, tmp_path):
        # When one assignment has an inline annotation (enters _merge_inline_comments)
        # and a second assignment has a standalone comment on the next line, that
        # standalone comment must stay separate even though it follows a `;` line —
        # exercises the `remaining.get(comment_text, 0) == 0` branch (153->157).
        entry = write(tmp_path, "entry.scad",
                      "width = 20; // [1:100]\n"
                      "height = 30;\n"
                      "// [5:50]\n"
                      "cube(width);")
        result = pack(entry)
        assert "width = 20; // [1:100]" in result
        assert "height = 30; // [5:50]" not in result
        assert "// [5:50]" in result


# ---------------------------------------------------------------------------
# Dual-namespace: same name defined as both function and module (BOSL pattern)
# ---------------------------------------------------------------------------

class TestDualNamespace:
    def test_both_defs_emitted_when_called_as_module(self, tmp_path):
        write(tmp_path, "lib.scad",
              "module foo(x) { cube(x); } "
              "function foo(x) = x + 1;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\nfoo(5);")
        result = pack(entry)
        assert "module foo" in result
        assert "function foo" in result

    def test_both_defs_emitted_when_called_as_function(self, tmp_path):
        write(tmp_path, "lib.scad",
              "module foo(x) { cube(x); } "
              "function foo(x) = x + 1;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(3);")
        result = pack(entry)
        assert "module foo" in result
        assert "function foo" in result

    def test_neither_def_emitted_when_not_called(self, tmp_path):
        write(tmp_path, "lib.scad",
              "module foo(x) { cube(x); } "
              "function foo(x) = x + 1;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ncube(10);")
        result = pack(entry)
        assert "foo" not in result

    def test_bosl_assertion_pattern(self, tmp_path):
        write(tmp_path, "compat.scad",
              "module assertion(succ, msg) { if (!succ) echo(str(\"ASSERT: \", msg)); }\n"
              "function assertion(succ, msg) = succ ? true : undef;")
        entry = write(tmp_path, "entry.scad",
                      "use <compat.scad>\nassertion(true, \"ok\");")
        result = pack(entry)
        assert "module assertion" in result
        assert "function assertion" in result

    def test_same_type_last_writer_wins(self, tmp_path):
        write(tmp_path, "lib.scad",
              "function foo(x) = x + 1;\n"
              "function foo(x) = x * 99;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(1);")
        result = pack(entry)
        assert "x * 99" in result
        assert "x + 1" not in result

    def test_order_preserved_module_before_function(self, tmp_path):
        write(tmp_path, "lib.scad",
              "module assertion(succ, msg) { if (!succ) echo(msg); }\n"
              "function assertion(succ, msg) = succ ? true : undef;")
        entry = write(tmp_path, "entry.scad",
                      "use <lib.scad>\nassertion(true, \"ok\");")
        result = pack(entry)
        assert result.index("module assertion") < result.index("function assertion")
