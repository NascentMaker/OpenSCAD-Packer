# OpenSCAD Packer

CLI tool that packs an OpenSCAD entry file and all its `use`/`include` dependencies into a single self-contained `.scad` file, using tree-shaking to include only the functions and modules that are actually called.

## Setup

```bash
uv sync --dev   # installs runtime deps + dev deps (pytest, coverage)
```

`uv sync` alone omits the dev group and will not install pytest.

## Running tests

```bash
uv run pytest           # runs all 83 tests with branch coverage (auto-enabled)
uv run pytest -v        # verbose output
uv run pytest -k foo    # filter by name
```

Coverage is wired into `addopts` in `pyproject.toml` — no extra flags needed. HTML report lands in `htmlcov/`.

## Running the CLI

```bash
uv run openscad-packer pack entry.scad -o packed.scad
uv run openscad-packer pack entry.scad -o packed.scad -L /path/to/extra/libs
uv run openscad-packer pack entry.scad          # stdout
```

## Key dependency

`openscad-parser` (PEG grammar, Arpeggio-based) provides the AST. Its public API lives in `openscad_parser.ast`. The pretty-printer (`openscad_parser.ast.pretty_print.to_openscad`) handles all output formatting — do not hand-roll OpenSCAD code generation.
