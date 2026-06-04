"""CLI tests for openscad_packer.cli using click's CliRunner."""
from pathlib import Path

import pytest
from click.testing import CliRunner

from openscad_packer.cli import cli


def write(directory: Path, name: str, content: str) -> Path:
    f = directory / name
    f.write_text(content)
    return f


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# pack — happy paths
# ---------------------------------------------------------------------------

class TestPackOutput:
    def test_outputs_to_stdout_by_default(self, runner, tmp_path):
        write(tmp_path, "lib.scad", "function foo(x) = x;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(1);")
        result = runner.invoke(cli, ["pack", str(entry)])
        assert result.exit_code == 0
        assert "foo" in result.output

    def test_output_to_file(self, runner, tmp_path):
        write(tmp_path, "lib.scad", "function foo(x) = x;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = foo(1);")
        out = tmp_path / "packed.scad"
        result = runner.invoke(cli, ["pack", str(entry), "-o", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        assert "foo" in out.read_text()

    def test_output_file_long_flag(self, runner, tmp_path):
        entry = write(tmp_path, "entry.scad", "cube(10);")
        out = tmp_path / "packed.scad"
        result = runner.invoke(cli, ["pack", str(entry), "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_stdout_does_not_include_written_to_message(self, runner, tmp_path):
        entry = write(tmp_path, "entry.scad", "cube(10);")
        result = runner.invoke(cli, ["pack", str(entry)])
        assert "Written to" not in result.output

    def test_file_output_reports_written_to(self, runner, tmp_path):
        entry = write(tmp_path, "entry.scad", "cube(10);")
        out = tmp_path / "packed.scad"
        result = runner.invoke(cli, ["pack", str(entry), "-o", str(out)])
        assert "Written to" in result.output

    def test_tree_shaking_applied_in_output(self, runner, tmp_path):
        write(tmp_path, "lib.scad",
              "function used(x) = x; function unused(x) = 99;")
        entry = write(tmp_path, "entry.scad", "use <lib.scad>\ny = used(1);")
        result = runner.invoke(cli, ["pack", str(entry)])
        assert result.exit_code == 0
        assert "used" in result.output
        assert "unused" not in result.output


# ---------------------------------------------------------------------------
# pack — library path flag
# ---------------------------------------------------------------------------

class TestLibraryPathFlag:
    def test_short_flag_resolves_library(self, runner, tmp_path):
        lib_dir = tmp_path / "libs"
        lib_dir.mkdir()
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        write(lib_dir, "mylib.scad", "function triple(x) = x * 3;")
        entry = write(proj_dir, "entry.scad", "use <mylib.scad>\ny = triple(4);")
        result = runner.invoke(cli, ["pack", str(entry), "-L", str(lib_dir)])
        assert result.exit_code == 0
        assert "triple" in result.output

    def test_long_flag_resolves_library(self, runner, tmp_path):
        lib_dir = tmp_path / "libs"
        lib_dir.mkdir()
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        write(lib_dir, "mylib.scad", "function triple(x) = x * 3;")
        entry = write(proj_dir, "entry.scad", "use <mylib.scad>\ny = triple(4);")
        result = runner.invoke(cli, ["pack", str(entry), "--library-path", str(lib_dir)])
        assert result.exit_code == 0
        assert "triple" in result.output

    def test_multiple_library_paths(self, runner, tmp_path):
        dir1 = tmp_path / "lib1"
        dir1.mkdir()
        dir2 = tmp_path / "lib2"
        dir2.mkdir()
        proj = tmp_path / "project"
        proj.mkdir()
        write(dir1, "a.scad", "function aaa(x) = x;")
        write(dir2, "b.scad", "function bbb(x) = x;")
        entry = write(proj, "entry.scad",
                      "use <a.scad>\nuse <b.scad>\nx = aaa(1);\ny = bbb(2);")
        result = runner.invoke(cli, [
            "pack", str(entry), "-L", str(dir1), "-L", str(dir2)
        ])
        assert result.exit_code == 0
        assert "aaa" in result.output
        assert "bbb" in result.output


# ---------------------------------------------------------------------------
# pack — error cases
# ---------------------------------------------------------------------------

class TestPackErrors:
    def test_missing_input_file_exits_nonzero(self, runner):
        result = runner.invoke(cli, ["pack", "does_not_exist.scad"])
        assert result.exit_code != 0

    def test_unresolvable_use_exits_nonzero(self, runner, tmp_path):
        entry = write(tmp_path, "entry.scad", "use <missing.scad>\ncube(10);")
        result = runner.invoke(cli, ["pack", str(entry)])
        assert result.exit_code != 0

    def test_unresolvable_use_names_missing_file(self, runner, tmp_path):
        entry = write(tmp_path, "entry.scad", "use <missing_lib.scad>\ncube(10);")
        result = runner.invoke(cli, ["pack", str(entry)])
        assert "missing_lib.scad" in result.output

    def test_unresolvable_include_exits_nonzero(self, runner, tmp_path):
        entry = write(tmp_path, "entry.scad", "include <missing.scad>")
        result = runner.invoke(cli, ["pack", str(entry)])
        assert result.exit_code != 0

    def test_nonexistent_library_path_dir_exits_nonzero(self, runner, tmp_path):
        entry = write(tmp_path, "entry.scad", "cube(10);")
        result = runner.invoke(cli, ["pack", str(entry), "-L", "/nonexistent/dir"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# pack — help
# ---------------------------------------------------------------------------

class TestHelp:
    def test_pack_help_exits_zero(self, runner):
        result = runner.invoke(cli, ["pack", "--help"])
        assert result.exit_code == 0

    def test_pack_help_mentions_input(self, runner):
        result = runner.invoke(cli, ["pack", "--help"])
        assert "INPUT" in result.output

    def test_pack_help_mentions_output_option(self, runner):
        result = runner.invoke(cli, ["pack", "--help"])
        assert "--output" in result.output

    def test_pack_help_mentions_library_path(self, runner):
        result = runner.invoke(cli, ["pack", "--help"])
        assert "--library-path" in result.output

    def test_root_help_exits_zero(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_root_help_lists_pack_command(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert "pack" in result.output
