import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_default_docker_dependencies_include_pypdf():
    requirements = (
        (ROOT / "deploy" / "docker" / "requirements.txt").read_text().splitlines()
    )

    assert "pypdf" in requirements


def test_stream_handler_preserves_requested_scraping_strategy():
    tree = ast.parse((ROOT / "deploy" / "docker" / "api.py").read_text())
    handler = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "handle_stream_crawl_request"
    )
    assigned_attributes = {
        target.attr
        for node in ast.walk(handler)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Attribute)
    }

    assert "scraping_strategy" not in assigned_attributes
