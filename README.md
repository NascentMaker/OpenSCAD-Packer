# OpenSCAD Packer

Pack an OpenSCAD entry file and all its `use`/`include` dependencies into a single self-contained `.scad` file.

Instead of distributing a project as a directory tree of files (and requiring recipients to have the same libraries installed), OpenSCAD Packer bundles everything into one file. It uses **tree-shaking** to include only the functions and modules that are actually called — directly or transitively — so the output stays lean even when pulling from large libraries.

## How it works

- `use <lib.scad>` — the library is parsed and only the reachable function and module definitions are inlined. Variables and top-level calls are discarded (matching OpenSCAD's own `use` semantics).
- `include <file.scad>` — function and module definitions are tree-shaken into the output; top-level assignments and module calls are always preserved (they affect variables and rendered geometry).
- Libraries that cannot be found cause an immediate error with a clear message. Pass extra search directories with `-L` if your libraries live outside the standard OpenSCAD path.

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install openscad-packer
```

This installs the `openscad-packer` command globally via uv's tool isolation.

Alternatively, add it as a dependency in your own uv project:

```bash
uv add openscad-packer
```

## Usage

```
openscad-packer pack [OPTIONS] INPUT

Arguments:
  INPUT                   Entry .scad file to pack.

Options:
  -o, --output PATH       Output file. Defaults to stdout.
  -L, --library-path PATH Extra library search directory (repeatable).
  --help
```

### Examples

Pack to a file:

```bash
openscad-packer pack my_model.scad -o my_model_packed.scad
```

Pack to stdout (useful for piping or inspection):

```bash
openscad-packer pack my_model.scad
```

Point to libraries that are not on the standard OpenSCAD path:

```bash
openscad-packer pack my_model.scad -o packed.scad -L ./vendor/BOSL2 -L ./vendor/NopSCADlib
```

### Library search order

For each `use`/`include` path, the tool searches in this order:

1. Directories supplied via `-L` (in the order given)
2. The directory containing the file that references the library
3. Directories in the `OPENSCADPATH` environment variable
4. The platform default: `~/Documents/OpenSCAD/libraries`

## Developer guide

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) — used for environment management and running the tool

### Clone and set up

```bash
git clone https://github.com/NascentMaker/OpenSCAD-Packer.git
cd OpenSCAD-Packer
uv sync --dev
```

`uv sync --dev` creates a virtual environment at `.venv/`, installs all runtime dependencies, and installs the dev group (pytest, pytest-cov, coverage).

> **Note:** `uv sync` without `--dev` omits the dev group and will not install pytest.

### Run the CLI locally

```bash
uv run openscad-packer pack entry.scad -o packed.scad
```

### Run the tests

```bash
uv run pytest
```

Branch coverage is enabled automatically. After the run, an HTML report is written to `htmlcov/index.html`.

To run a subset of tests:

```bash
uv run pytest -v -k "tree_shak"
```

### Project structure

```
openscad_packer/
    cli.py        # click entry point — pack command
    packer.py     # Packer class: collect phase + assemble phase
    shaker.py     # AST walker, tree-shaking, reachability analysis
    resolver.py   # Library path resolution
tests/
    conftest.py
    test_cli.py
    test_packer.py
    test_resolver.py
    test_shaker.py
```

### Building a distribution

```bash
uv build
```

This produces a wheel and sdist in `dist/`. To publish to PyPI:

```bash
uv publish
```

## License

OpenSCAD Packer is released under the [GNU Affero General Public License v3.0](LICENSE).
