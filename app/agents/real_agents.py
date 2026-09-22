from __future__ import annotations
from typing import Any
from app.agents.base import BaseAgent
from app.providers.base import LLMProvider
from app.research.base import ResearchProvider


class LLMResearchAgent(BaseAgent):
    name = "research"

    def __init__(self, llm: LLMProvider, research: ResearchProvider | None = None):
        self.llm = llm
        self.research = research

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        topic = input_data["topic"]
        memory = input_data.get("channel", {}).get("memory", {})
        idea = input_data.get("idea_context", {})
        external = await self.research.search(query=topic, max_results=8) if self.research else {"results": []}
        result = await self.llm.generate_json(
            system=(
                "Return research JSON with keywords, audience_questions, content_gaps, competitor_findings, and source_summary. "
                "Use the supplied external search results as evidence and preserve URLs. Avoid inventing sources."
            ),
            user=f"""Research this YouTube topic: {topic}\n\nSelected idea context: {idea}\n\nChannel memory: {memory}\n\nExternal search results: {external.get('results', [])}""",
        )
        return {
            "topic": topic,
            "external_research": external,
            **result,
        }


class LLMScriptAgent(BaseAgent):
    name = "script"

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        topic = input_data["research"]["topic"]
        idea = input_data.get("idea_context", {})
        memory = input_data.get("channel", {}).get("memory", {})
        research = input_data.get("research", {})
        result = await self.llm.generate_json(
            system=(
                "Return script JSON: title, hook, sections[]. Each section needs type, duration, text. "
                "Write a factual, source-aware YouTube script; do not invent facts. Honor selected hook/angle and learned channel patterns."
            ),
            user=f"""Write a YouTube script about: {topic}\n\nSelected idea: {idea}\n\nResearch: {research}\n\nChannel memory: {memory}""",
        )
        if idea.get("title") and not result.get("title"):
            result["title"] = idea["title"]
        if idea.get("hook") and not result.get("hook"):
            result["hook"] = idea["hook"]
        return self._normalize_script_result(result, topic, idea)

    @staticmethod
    def _normalize_script_result(result: dict[str, Any], topic: str, idea: dict[str, Any]) -> dict[str, Any]:
        """Accept PR #1 flat scenes while preserving the current Scene Graph contract."""
        if isinstance(result.get("sections"), list) and result.get("sections"):
            return result
        raw_scenes = result.get("scenes") if isinstance(result.get("scenes"), list) else []
        sections: list[dict[str, Any]] = []
        for index, scene in enumerate(raw_scenes, start=1):
            if not isinstance(scene, dict):
                continue
            text = str(scene.get("text") or scene.get("narration") or "").strip()
            try:
                duration = max(float(scene.get("duration", 5) or 5), 1.0)
            except (TypeError, ValueError):
                duration = 5.0
            sections.append({
                "type": "intro" if index == 1 else "outro" if index == len(raw_scenes) else "main",
                "duration": duration,
                "text": text,
                "visual_prompt": str(scene.get("visual_prompt") or scene.get("visual") or "").strip(),
            })
        if sections:
            result["sections"] = sections
        else:
            result["sections"] = [
                {
                    "type": "intro",
                    "duration": 8.0,
                    "text": str(idea.get("hook") or f"Почему тема «{topic}» важна прямо сейчас."),
                    "visual_prompt": f"cinematic opening visual about {topic}",
                },
                {
                    "type": "main",
                    "duration": 16.0,
                    "text": f"Разберём ключевые идеи, примеры и практические выводы по теме «{topic}».",
                    "visual_prompt": f"cinematic documentary b-roll explaining {topic}",
                },
                {
                    "type": "outro",
                    "duration": 7.0,
                    "text": f"Главный вывод: используйте эти идеи как основу для следующего шага по теме «{topic}».",
                    "visual_prompt": f"cinematic closing shot summarizing {topic}",
                },
            ]
        result.setdefault("title", idea.get("title") or topic)
        result.setdefault("hook", idea.get("hook") or str(result["sections"][0].get("text") or ""))
        return result

