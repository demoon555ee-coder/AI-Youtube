from __future__ import annotations

import ast
from pathlib import Path


ROUTE_OWNERSHIP_REQUIREMENTS = {
    "channel_dashboard": "_get_owned_channel",
    "channel_projects": "_get_owned_channel",
    "create_project": "_get_owned_channel",
    "run_project": "_get_owned_project",
    "retry_project": "_get_owned_project",
    "get_project": "_get_owned_project",
    "get_project_video": "_get_owned_project",
    "get_project_subtitles": "_get_owned_project",
    "get_project_thumbnail": "_get_owned_project",
    "get_project_assets": "_get_owned_project",
}


def _route_functions() -> dict[str, ast.AsyncFunctionDef]:
    source = Path("app/api/routes.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
    }


def _calls(node: ast.AsyncFunctionDef, function_name: str) -> bool:
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == function_name
        for item in ast.walk(node)
    )


def test_project_and_dashboard_routes_require_principal_and_ownership() -> None:
    routes = _route_functions()

    for route_name, ownership_helper in ROUTE_OWNERSHIP_REQUIREMENTS.items():
        node = routes[route_name]
        arguments = {arg.arg for arg in node.args.args}
        assert "principal" in arguments, f"{route_name} must require a Principal dependency"
        assert _calls(node, ownership_helper), (
            f"{route_name} must enforce resource ownership through {ownership_helper}"
        )
