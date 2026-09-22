from app.agents.real_agents import LLMResearchAgent, LLMScriptAgent
from app.content.strategy import ContentStrategyEngine


class FakeLLM:
    async def generate_json(self, *, system, user):
        return {"title": "LLM title", "hook": "LLM hook", "sections": [{"type": "hook", "duration": 5, "text": "Hello"}]} if "script" in system.lower() else {"keywords": ["ai"], "audience_questions": [], "content_gaps": [], "sources": []}


async def _run():
    context = {
        "topic": "AI agents",
        "channel": {"name": "AI Lab", "niche": "AI technology", "language": "en", "memory": {"version": 3, "learned_patterns": []}},
        "idea_context": {"title": "AI Agents — What Happens Next?", "hook": "Most people think AI agents are simple.", "angle": "future impact", "strategy": {"goal": "growth"}},
    }
    research = await LLMResearchAgent(FakeLLM()).run(context)
    context["research"] = {"topic": context["topic"], **research}
    script = await LLMScriptAgent(FakeLLM()).run(context)
    assert script["title"]
    assert "sections" in script
