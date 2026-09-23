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


def _route_functions(path: str) -> dict[str, ast.AsyncFunctionDef]:
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
    }


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _calls(node: ast.AsyncFunctionDef, function_name: str) -> bool:
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == function_name
        for item in ast.walk(node)
    )


def test_project_and_dashboard_routes_require_principal_and_ownership() -> None:
    routes = _route_functions("app/api/routes.py")

    for route_name, ownership_helper in ROUTE_OWNERSHIP_REQUIREMENTS.items():
        node = routes[route_name]
        arguments = {arg.arg for arg in node.args.args}
        assert "principal" in arguments, f"{route_name} must require a Principal dependency"
        assert _calls(node, ownership_helper), (
            f"{route_name} must enforce resource ownership through {ownership_helper}"
        )


def test_workflow_research_and_intelligence_boundaries_are_authenticated() -> None:
    expectations = {
        "app/api/workflows.py": (
            {"get_workflow", "cancel_workflow", "workflow_events"},
            "principal.scope_key",
        ),
        "app/api/research.py": ({"run_research"}, "principal.scope_key"),
        "app/api/intelligence.py": (
            {"intelligence_overview", "intelligence_blueprints", "intelligence_blueprint"},
            "principal.scope_key",
        ),
    }
    expectations.update(
        {
            "app/api/brain.py": (
                {"rebuild_channel_brain", "get_channel_brain", "optimize_channel_video"},
                "principal.scope_key",
            ),
            "app/api/content.py": (
                {"content_generate_ideas", "content_list_ideas", "content_select_idea", "content_create_project"},
                "principal.scope_key",
            ),
            "app/api/experiments.py": (
                {"list_experiments", "create_experiment", "create_from_optimization", "add_observation", "evaluate_experiment", "close_experiment"},
                "principal.scope_key",
            ),
            "app/api/opportunity_intelligence.py": (
                {"analyze", "decisions", "runs"},
                "principal.scope_key",
            ),
            "app/api/research_intelligence.py": (
                {"scan", "opportunities", "graph", "generate_ideas_from_opportunities"},
                "principal.scope_key",
            ),
        }
    )

    for path, (route_names, ownership_marker) in expectations.items():
        source = _source(path)
        routes = _route_functions(path)
        assert ownership_marker in source, f"{path} must enforce ownership"
        for route_name in route_names:
            node = routes[route_name]
            arguments = {arg.arg for arg in node.args.args}
            assert "principal" in arguments, f"{path}:{route_name} must require a Principal dependency"
