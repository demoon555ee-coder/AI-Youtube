from __future__ import annotations
from app.agents.real_agents import LLMResearchAgent, LLMScriptAgent
from app.agents.scout import TopicScoutAgent
from app.agents.storyboard import StoryboardAgent
from app.agents.production import ProductionAgent
from app.agents.demo_agents import EditorAgent
from app.agents.qa import QAAgent
from app.agents.scene_director import SceneDirectorAgent
from app.agents.publisher import YouTubePublisherAgent
from app.providers import get_llm
from app.research import get_research_provider


def build_agent(name: str, *, provider: str | None = None, config: dict | None = None):
    cfg = config or {}
    if name == "scout":
        return TopicScoutAgent(get_llm(provider, cfg))
    if name == "script":
        return LLMScriptAgent(get_llm(provider, cfg))
    if name == "scene_director":
        return SceneDirectorAgent(get_llm(provider, cfg))
    if name == "research":
        research = get_research_provider(provider, cfg)
        llm_provider = cfg.get("llm_provider")
        llm_config = cfg.get("llm_config") or {}
        return LLMResearchAgent(get_llm(llm_provider, llm_config), research)
    if name == "qa":
        return QAAgent()
    if name == "publisher":
        return YouTubePublisherAgent(cfg.get("_db"))
    if name == "storyboard":
        return StoryboardAgent()
    if name == "production":
        return ProductionAgent(
            image_provider=cfg.get("image_provider") or provider,
            image_config=cfg.get("image_config") or cfg,
            video_provider=cfg.get("video_provider"),
            video_config=cfg.get("video_config") or {},
            db=cfg.get("_db"),
            organization_id=cfg.get("_organization_id"),
            portfolio_id=cfg.get("_portfolio_id"),
            channel_id=cfg.get("_channel_id"),
            agent_run_id=cfg.get("_agent_run_id"),
            workflow_attempt=int(cfg.get("_workflow_attempt") or 1),
        )
    if name == "editor":
        return EditorAgent()
    if name == "thumbnail":
        return None
    raise ValueError(f"Unknown agent: {name}")


def build_agents():
    return {name: build_agent(name) for name in ["scout", "research", "script", "storyboard", "scene_director", "production", "editor", "qa", "publisher"]}
