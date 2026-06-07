"""Unit tests for openscad_packer.shaker."""
from pathlib import Path
from typing import Any

from openscad_parser.ast import getASTfromFile
from openscad_parser.ast.nodes import FunctionDeclaration, ModuleDeclaration

from openscad_packer.shaker import collect_called_names, compute_reachable


def parse(tmp_path: Path, content: str) -> list[Any]:
    test_file = tmp_path / "test.scad"
    test_file.write_text(content)
    return getASTfromFile(str(test_file), process_includes=False) or []


def make_pool(tmp_path: Path, content: str) -> dict[str, list]:
    """Parse content and return a list-valued pool dict.

    This mirrors the private ``_add_to_pool`` behavior in ``openscad_packer.packer``.
    """
    nodes = parse(tmp_path, content)
    pool: dict[str, list] = {}
    for node in nodes:
        if isinstance(node, (FunctionDeclaration, ModuleDeclaration)):
            name = node.name.name
            if name not in pool:
                pool[name] = []
            # Keep at most one declaration per (name, declaration type).
            # If another declaration of the same type appears later, it replaces
            # the earlier one (latest-wins), while a different type is kept too
            # (for example, both a function and a module named "foo").
            replace_at: int | None = None
            for i, existing in enumerate(pool[name]):
                if isinstance(existing, type(node)):
                    replace_at = i
                    break
            if replace_at is not None:
                pool[name][replace_at] = node
            else:
                pool[name].append(node)
    return pool


class TestCollectCalledNames:
    def test_collects_module_call(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "cube(10);"))
        assert "cube" in names

    def test_collects_multiple_module_calls(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "cube(10); sphere(5);"))
        assert "cube" in names
        assert "sphere" in names

    def test_collects_function_call_in_expression(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "x = sin(45);"))
        assert "sin" in names

    def test_collects_nested_module_calls(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "translate([1,0,0]) cube(5);"))
        assert "translate" in names
        assert "cube" in names

    def test_collects_call_inside_function_body(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "function foo(x) = bar(x) + 1;"))
        assert "bar" in names

    def test_collects_call_inside_module_body(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "module foo() { bar(); baz(); }"))
        assert "bar" in names
        assert "baz" in names

    def test_collects_call_in_nested_module_body(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "module foo() { translate([0,0,1]) cube(3); }"))
        assert "translate" in names
        assert "cube" in names

    def test_collects_function_call_inside_module(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "module foo(s) { cube(scale(s)); }"))
        assert "scale" in names
        assert "cube" in names

    def test_collects_call_in_assignment_rhs(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "x = double(5);"))
        assert "double" in names

    def test_empty_nodes_returns_empty_set(self):
        names = collect_called_names([])
        assert names == set()

    def test_does_not_collect_declaration_names(self, tmp_path):
        names = collect_called_names(parse(tmp_path, "function foo(x) = x; module bar() { cube(1); }"))
        # foo and bar are declared, not called — they should not be in the call set
        assert "foo" not in names
        assert "bar" not in names
        assert "cube" in names

    def test_collects_chained_calls(self, tmp_path):
        # translate(...) rotate(...) cube(...)
        names = collect_called_names(parse(tmp_path, "translate([1,0,0]) rotate([0,0,45]) cube(5);"))
        assert "translate" in names
        assert "rotate" in names
        assert "cube" in names

    def test_does_not_collect_non_identifier_primary_calls(self, tmp_path):
        # (function(x) x*2)(5) — PrimaryCall where left is a FunctionLiteral, not Identifier
        names = collect_called_names(parse(tmp_path, "y = (function(x) x*2)(5);"))
        # The callee is a FunctionLiteral (not an Identifier), so the call site
        # contributes nothing. The body x*2 has no inner calls either, so the
        # full result must be empty.
        assert names == set()


class TestComputeReachable:
    def test_empty_seed_returns_empty(self, tmp_path):
        pool = make_pool(tmp_path, "function foo(x) = x;")
        assert compute_reachable(set(), pool) == set()

    def test_seed_not_in_pool_returns_empty(self, tmp_path):
        pool = make_pool(tmp_path, "function foo(x) = x;")
        # "sin" is not in the pool (it's a built-in)
        assert compute_reachable({"sin"}, pool) == set()

    def test_direct_reachability(self, tmp_path):
        pool = make_pool(tmp_path, "function foo(x) = x + 1; function bar(x) = x * 2;")
        reachable = compute_reachable({"foo"}, pool)
        assert "foo" in reachable
        assert "bar" not in reachable

    def test_transitive_reachability(self, tmp_path):
        pool = make_pool(
            tmp_path,
            "function a(x) = b(x); function b(x) = x * 2; function unused(x) = 99;"
        )
        reachable = compute_reachable({"a"}, pool)
        assert "a" in reachable
        assert "b" in reachable
        assert "unused" not in reachable

    def test_mutual_recursion_terminates(self, tmp_path):
        pool = make_pool(
            tmp_path,
            "function is_even(n) = n == 0 ? true : is_odd(n - 1); "
            "function is_odd(n) = n == 0 ? false : is_even(n - 1);"
        )
        reachable = compute_reachable({"is_even"}, pool)
        assert "is_even" in reachable
        assert "is_odd" in reachable

    def test_reachability_from_multiple_seeds(self, tmp_path):
        pool = make_pool(
            tmp_path,
            "function a(x) = x; function b(x) = x; function unused(x) = 99;"
        )
        reachable = compute_reachable({"a", "b"}, pool)
        assert "a" in reachable
        assert "b" in reachable
        assert "unused" not in reachable

    def test_module_reachability(self, tmp_path):
        pool = make_pool(
            tmp_path,
            "module outer(s) { inner(s); } module inner(s) { cube(s); } module unused() { sphere(1); }"
        )
        reachable = compute_reachable({"outer"}, pool)
        assert "outer" in reachable
        assert "inner" in reachable
        assert "unused" not in reachable

    def test_builtins_in_seed_ignored(self, tmp_path):
        pool = make_pool(tmp_path, "function foo(x) = x;")
        # "cube" is a built-in — not in pool — reachability stays empty
        reachable = compute_reachable({"cube", "sphere"}, pool)
        assert reachable == set()

    def test_deep_chain(self, tmp_path):
        pool = make_pool(
            tmp_path,
            "function a(x) = b(x); function b(x) = c(x); function c(x) = d(x); "
            "function d(x) = x; function unused(x) = 0;"
        )
        reachable = compute_reachable({"a"}, pool)
        assert reachable == {"a", "b", "c", "d"}

    def test_dual_namespace_traverses_all_defs(self, tmp_path):
        """When pool["foo"] holds both a module and a function, reachability must
        traverse both — names called by either definition become reachable."""
        pool = make_pool(
            tmp_path,
            "module foo(x) { bar(x); } "
            "function foo(x) = baz(x); "
            "module bar(x) { cube(x); } "
            "function baz(x) = x * 2; "
            "function unused(x) = 0;"
        )
        reachable = compute_reachable({"foo"}, pool)
        assert "foo" in reachable
        assert "bar" in reachable      # called by module foo
        assert "baz" in reachable      # called by function foo
        assert "unused" not in reachable
