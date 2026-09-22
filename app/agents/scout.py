from __future__ import annotations

import json
from typing import Any

from app.agents.base import BaseAgent
from app.providers.base import LLMProvider


class TopicScoutAgent(BaseAgent):
    """Planner-safe trend scout adapted from PR #1 without direct API/auth side effects."""

    name = "scout"

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        seed = str(input_data.get("topic") or input_data.get("goal") or "").strip()
        niche = str(input_data.get("niche") or "technology and AI").strip()
        if getattr(self.llm, "name", "") == "mock":
            return self._fallback(seed, niche)
        result = await self.llm.generate_json(
            system=(
                "Return JSON only with topic, keywords, trend_score, rationale. "
                "trend_score must be 0..100. Select one useful YouTube topic; do not invent external evidence."
            ),
            user=json.dumps({"seed": seed, "niche": niche, "goal": input_data.get("goal", "")}, ensure_ascii=False),
        )
        return self._normalize(result, seed, niche)

    @staticmethod
    def _normalize(result: dict[str, Any], seed: str, niche: str) -> dict[str, Any]:
        fallback = TopicScoutAgent._fallback(seed, niche)
        topic = str(result.get("topic") or fallback["topic"]).strip()
        keywords = result.get("keywords") if isinstance(result.get("keywords"), list) else fallback["keywords"]
        keywords = [str(x).strip() for x in keywords if str(x).strip()][:12] or fallback["keywords"]
        try:
            trend_score = max(0.0, min(100.0, float(result.get("trend_score", fallback["trend_score"]))))
        except (TypeError, ValueError):
            trend_score = fallback["trend_score"]
        return {
            "topic": topic,
            "keywords": keywords,
            "trend_score": trend_score,
            "rationale": str(result.get("rationale") or fallback["rationale"]),
        }

    @staticmethod
    def _fallback(seed: str, niche: str) -> dict[str, Any]:
        topic = seed or f"Актуальные тренды в {niche}"
        return {
            "topic": topic,
            "keywords": [x for x in [niche, "YouTube", "тренды", "AI"] if x],
            "trend_score": 50.0,
            "rationale": "Deterministic scout fallback; replace with an LLM provider for live topic discovery.",
        }
