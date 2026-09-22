import pytest

from app.agents.factory import build_agent
from app.agents.real_agents import LLMScriptAgent
from app.planner.service import DEFAULT_BLUEPRINT
from app.providers.mock import MockLLMProvider
from app.runtime.service import DEFAULT_AGENTS
from app.governance.service import DEFAULT_ACTIONS


@pytest.mark.asyncio
async def test_pr1_scout_is_a_governed_runtime_capability():
    scout = build_agent("scout", provider="mock")
    result = await scout.run({"goal": "AI video trends"})
    assert result["topic"]
    assert result["keywords"]
    assert 0 <= result["trend_score"] <= 100
    assert "topic_scout" in DEFAULT_AGENTS["scout"]["capabilities"]
    assert DEFAULT_ACTIONS["topic_scout"]["automation_mode"] == "auto"


def test_default_planner_pipeline_uses_scout_and_valid_scene_dependency():
    by_key = {node["node_key"]: node for node in DEFAULT_BLUEPRINT}
    assert by_key["scout"]["capability"] == "topic_scout"
    assert by_key["research"]["deps"] == ["scout"]
    assert by_key["production"]["deps"] == ["scene_director"]


@pytest.mark.asyncio
async def test_pr1_scriptwriter_scene_output_maps_to_current_scene_graph():
    agent = LLMScriptAgent(MockLLMProvider())
    result = agent._normalize_script_result(
        {
            "title": "Example",
            "scenes": [
                {"scene_id": 1, "text": "Hook", "visual_prompt": "intro", "duration": 5},
                {"scene_id": 2, "text": "Main", "visual_prompt": "broll", "duration": 8},
            ],
        },
        "Example topic",
        {},
    )
    assert [s["type"] for s in result["sections"]] == ["intro", "outro"]
    assert result["sections"][0]["visual_prompt"] == "intro"
    assert result["sections"][1]["duration"] == 8.0



def test_planner_composes_upstream_outputs_for_next_node():
    from types import SimpleNamespace
    from uuid import uuid4
    from app.planner.service import AgentPlannerService

    plan = SimpleNamespace(id=uuid4(), context={"niche": "AI"})
    scout = SimpleNamespace(node_key="scout", output_data={"topic": "AI video", "keywords": ["AI"], "trend_score": 91})
    research = SimpleNamespace(node_key="research", output_data={"source_summary": "verified"})
    script = SimpleNamespace(id=uuid4(), node_key="script", input_data={"format": "long-form"}, output_data={})

    payload = AgentPlannerService._compose_task_input(plan, script, [research])
    assert payload["niche"] == "AI"
    assert payload["format"] == "long-form"
    assert payload["research"] == {"source_summary": "verified"}
    assert payload["upstream_outputs"]["research"]["source_summary"] == "verified"

    scout_payload = AgentPlannerService._compose_task_input(plan, script, [scout])
    assert scout_payload["topic"] == "AI video"
    assert scout_payload["keywords"] == ["AI"]
    assert scout_payload["scout"]["trend_score"] == 91


def test_agent_task_worker_uses_runtime_factory_and_isolated_cost():
    from app.workflows.agent_worker import AgentTaskWorker
    from decimal import Decimal

    assert AgentTaskWorker._actual_cost({"actual_cost_usd": 2}, 1.5) == Decimal("1.5")
    assert AgentTaskWorker._actual_cost({"usage": {"actual_cost_usd": 0.25}}, 1.5) == Decimal("0.25")
    assert AgentTaskWorker._actual_cost({}, 1.5) == Decimal("0")


def test_publish_capability_is_governed_and_after_qa():
    from app.governance.service import DEFAULT_ACTIONS
    from app.planner.service import DEFAULT_BLUEPRINT
    from app.runtime.service import DEFAULT_AGENTS

    by_key = {n["node_key"]: n for n in DEFAULT_BLUEPRINT}
    assert by_key["publish"]["deps"] == ["qa"]
    assert by_key["publish"]["action_type"] == "publish"
    assert "publish" in DEFAULT_AGENTS["publisher"]["capabilities"]
    assert DEFAULT_ACTIONS["publish"]["require_human_approval"] is True


def test_youtube_publish_routes_to_runtime_task_not_direct_upload():
    from pathlib import Path
    youtube_api = Path("app/api/youtube.py").read_text(encoding="utf-8")
    assert "AgentRuntimeService(db).create_task" in youtube_api
    assert "action_type=\"publish\"" in youtube_api
    assert "await publish(" not in youtube_api


def test_autopublish_queues_publisher_task():
    from pathlib import Path
    publisher = Path("app/services/autopilot_publisher.py").read_text(encoding="utf-8")
    assert "AgentRuntimeService(db).create_task" in publisher
    assert 'action_type="publish"' in publisher
    assert "upload_video(" not in publisher


def test_postpublish_feedback_is_learning_observation():
    import inspect
    from pathlib import Path
    from app.learning.service import AgentLearningService

    method = inspect.getsource(AgentLearningService.record_post_publish_feedback)
    assert 'source_type="post_publish"' in method
    assert 'youtube_video_id' in method
    service = Path("app/postpublish/service.py").read_text(encoding="utf-8")
    assert "_record_learning_feedback" in service
    assert "AgentLearningService(self.db).record_post_publish_feedback" in service


def test_auth_register_and_login_pass_request_then_principal_to_audit():
    import ast
    from pathlib import Path

    tree = ast.parse((Path("app/api/auth.py")).read_text(encoding="utf-8"))
    targets = {"auth_register", "auth_login"}
    checked = set()

    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef) or node.name not in targets:
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "write_audit":
                continue
            assert len(call.args) >= 3
            assert isinstance(call.args[0], ast.Name) and call.args[0].id == "db"
            assert isinstance(call.args[1], ast.Name) and call.args[1].id == "request"
            assert isinstance(call.args[2], ast.Call)
            assert isinstance(call.args[2].func, ast.Name) and call.args[2].func.id == "Principal"
            checked.add(node.name)

    assert checked == targets


def test_workflow_start_does_not_hold_project_lock_across_sessions():
    from pathlib import Path

    source = Path("app/api/routes.py").read_text(encoding="utf-8")
    start = source.index("async def run_project(")
    end = source.index("\n\n@router.post(\"/projects/{project_id}/retry\"", start)
    block = source[start:end]
    assert "await db.get(VideoProject, project_id, with_for_update=True)" not in block
    assert "WorkflowEngine(SessionLocal).create_or_get" in block
