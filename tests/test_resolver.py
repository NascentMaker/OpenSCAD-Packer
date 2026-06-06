"""Unit tests for openscad_packer.resolver."""
from pathlib import Path

from openscad_packer.resolver import resolve_library


def _write(directory: Path, name: str, content: str = "// stub") -> Path:
    f = directory / name
    f.write_text(content)
    return f


class TestExtraPaths:
    def test_finds_file_in_extra_path(self, tmp_path):
        lib = _write(tmp_path, "mylib.scad")
        result = resolve_library("", "mylib.scad", [str(tmp_path)])
        assert result is not None
        assert Path(result) == lib.resolve()

    def test_extra_paths_checked_in_order(self, tmp_path):
        dir1 = tmp_path / "first"
        dir1.mkdir()
        dir2 = tmp_path / "second"
        dir2.mkdir()
        lib1 = _write(dir1, "lib.scad", "// first")
        _write(dir2, "lib.scad", "// second")

        result = resolve_library("", "lib.scad", [str(dir1), str(dir2)])
        assert result is not None
        assert Path(result) == lib1.resolve()

    def test_second_extra_path_used_when_first_lacks_file(self, tmp_path):
        dir1 = tmp_path / "first"
        dir1.mkdir()
        dir2 = tmp_path / "second"
        dir2.mkdir()
        lib2 = _write(dir2, "lib.scad")

        result = resolve_library("", "lib.scad", [str(dir1), str(dir2)])
        assert result is not None
        assert Path(result) == lib2.resolve()

    def test_extra_path_wins_over_same_dir_as_curr_file(self, tmp_path):
        same_dir = tmp_path / "project"
        same_dir.mkdir()
        extra_dir = tmp_path / "libs"
        extra_dir.mkdir()

        _write(same_dir, "lib.scad", "// from same dir")
        lib_extra = _write(extra_dir, "lib.scad", "// from extra")

        curr_file = str(same_dir / "entry.scad")
        result = resolve_library(curr_file, "lib.scad", [str(extra_dir)])
        assert result is not None
        assert Path(result) == lib_extra.resolve()

    def test_returns_absolute_path(self, tmp_path):
        _write(tmp_path, "lib.scad")
        result = resolve_library("", "lib.scad", [str(tmp_path)])
        assert result is not None
        assert Path(result).is_absolute()


class TestFallback:
    def test_falls_back_to_same_dir_as_curr_file(self, tmp_path):
        lib = _write(tmp_path, "helpers.scad")
        curr_file = str(tmp_path / "entry.scad")  # file need not exist
        result = resolve_library(curr_file, "helpers.scad", [])
        assert result is not None
        assert Path(result) == lib.resolve()

    def test_returns_none_when_not_found(self, tmp_path):
        curr_file = str(tmp_path / "entry.scad")
        result = resolve_library(curr_file, "nonexistent.scad", [])
        assert result is None

    def test_returns_none_with_empty_extra_paths_and_no_file(self, tmp_path):
        result = resolve_library("", "nonexistent.scad", [])
        assert result is None

    def test_subdirectory_path_resolved(self, tmp_path):
        sub = tmp_path / "utils"
        sub.mkdir()
        lib = _write(sub, "math.scad")
        result = resolve_library("", "utils/math.scad", [str(tmp_path)])
        assert result is not None
        assert Path(result) == lib.resolve()
