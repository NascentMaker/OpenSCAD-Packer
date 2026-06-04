import pytest
from openscad_parser.ast import clear_ast_cache


@pytest.fixture(autouse=True)
def clear_parser_cache():
    """Clear the openscad_parser in-memory AST cache before each test.

    Prevents stale cached parses from leaking between tests that reuse
    the same file paths (possible when pytest reuses tmp_path slots).
    """
    clear_ast_cache()
    yield
    clear_ast_cache()
