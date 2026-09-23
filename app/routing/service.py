from __future__ import annotations
import os
import shutil
from dataclasses import asdict
from datetime import datetime
from typing import Any, Iterable
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Channel, CostEvent, Portfolio, PortfolioChannel, ProviderBudget, ProviderProfile, RoutingDecision
from app.portfolio.service import PortfolioService
from app.routing.policy import Candidate, TIER_ORDER, rank_candidates
from app.resilience.provider import ProviderReliabilityService

DEFAULTS: dict[str, list[dict[str, Any]]] = {
    "llm": [
        {"provider": "mock", "kind": "mock", "tier": "economy", "priority": 10, "unit": "request", "unit_cost_usd": 0.0, "capabilities": {"json": True}},
        {"provider": "openai_compatible", "kind": "openai_compatible", "tier": "standard", "priority": 100, "unit": "request", "unit_cost_usd": 0.0, "capabilities": {"json": True}},
    ],
    "research": [
        {"provider": "mock", "kind": "mock", "tier": "economy", "priority": 10, "unit": "request", "unit_cost_usd": 0.0, "capabilities": {"search": True}},
        {"provider": "http_json", "kind": "http_json", "tier": "standard", "priority": 100, "unit": "request", "unit_cost_usd": 0.0, "capabilities": {"search": True}},
    ],
    "visual": [
        {"provider": "mock_png", "kind": "mock_png", "tier": "economy", "priority": 10, "unit": "asset", "unit_cost_usd": 0.0, "capabilities": {"image": True, "generative": True}},
        {"provider": "pexels_photo", "kind": "pexels_photo", "tier": "standard", "priority": 95, "unit": "image", "unit_cost_usd": 0.0, "capabilities": {"image": True, "stock": True}},
        {"provider": "openai_image", "kind": "openai_image", "tier": "premium", "priority": 100, "unit": "image", "unit_cost_usd": 0.0, "capabilities": {"image": True, "generative": True}},
        {"provider": "http_image", "kind": "http_image", "tier": "standard", "priority": 80, "unit": "image", "unit_cost_usd": 0.0, "capabilities": {"image": True}},
        {"provider": "stability_image", "kind": "stability_image", "tier": "premium", "priority": 110, "unit": "image", "unit_cost_usd": 0.0, "capabilities": {"image": True, "generative": True}},
    ],
    "tts": [
        {"provider": "espeak", "kind": "espeak", "tier": "economy", "priority": 10, "unit": "minute", "unit_cost_usd": 0.0, "capabilities": {"voice": True}},
        {"provider": "openai_tts", "kind": "openai_tts", "tier": "premium", "priority": 100, "unit": "minute", "unit_cost_usd": 0.0, "capabilities": {"voice": True}},
        {"provider": "elevenlabs", "kind": "elevenlabs", "tier": "premium", "priority": 110, "unit": "minute", "unit_cost_usd": 0.0, "capabilities": {"voice": True}},
    ],
    "render": [
        {"provider": "remotion", "kind": "remotion", "tier": "standard", "priority": 100, "unit": "minute", "unit_cost_usd": 0.0, "capabilities": {"render": True}},
        {"provider": "ffmpeg", "kind": "ffmpeg", "tier": "economy", "priority": 10, "unit": "minute", "unit_cost_usd": 0.0, "capabilities": {"render": True}},
    ],
    "image": [
        {"provider": "mock_png", "kind": "mock_png", "tier": "economy", "priority": 10, "unit": "image", "unit_cost_usd": 0.0, "capabilities": {"image": True, "generative": True}},
        {"provider": "pexels_photo", "kind": "pexels_photo", "tier": "standard", "priority": 95, "unit": "image", "unit_cost_usd": 0.0, "capabilities": {"image": True, "stock": True}},
        {"provider": "openai_image", "kind": "openai_image", "tier": "premium", "priority": 100, "unit": "image", "unit_cost_usd": 0.0, "capabilities": {"image": True, "generative": True}},
        {"provider": "http_image", "kind": "http_image", "tier": "standard", "priority": 80, "unit": "image", "unit_cost_usd": 0.0, "capabilities": {"image": True}},
    ],
    "video": [
        {"provider": "mock_video", "kind": "mock_video", "tier": "economy", "priority": 10, "unit": "second", "unit_cost_usd": 0.0, "capabilities": {"video": True, "generative": True}},
        {"provider": "pexels_video", "kind": "pexels_video", "tier": "standard", "priority": 120, "unit": "second", "unit_cost_usd": 0.0, "capabilities": {"video": True, "stock_broll": True}},
        {"provider": "http_video", "kind": "http_video", "tier": "premium", "priority": 100, "unit": "second", "unit_cost_usd": 0.0, "capabilities": {"video": True}},
        {"provider": "runway", "kind": "runway", "tier": "premium", "priority": 110, "unit": "second", "unit_cost_usd": 0.0, "capabilities": {"video": True, "generative": True}},
    ],
}

SETTINGS_PROVIDER = {
    "llm": lambda: settings.llm_provider,
    "research": lambda: settings.research_provider,
    "visual": lambda: settings.visual_provider,
    "tts": lambda: settings.tts_provider,
    "render": lambda: "remotion" if settings.render_engine in {"remotion", "auto"} else "ffmpeg",
    "image": lambda: settings.image_provider,
    "video": lambda: settings.video_provider,
}


class ProviderRouter:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.portfolio_service = PortfolioService(db)

    async def ensure_portfolio(self, owner_id: str = "local-user") -> Portfolio:
        return await self.portfolio_service.ensure(owner_id)

    def _runtime_available(self, candidate: Candidate) -> bool:
        if candidate.kind == "mock":
            return True
        if candidate.kind in {"mock_png", "mock_video", "espeak", "ffmpeg"}:
            return True
        if candidate.kind == "remotion":
            return bool(shutil.which(settings.remotion_node_bin) and os.path.isdir(settings.remotion_project_dir))
        cfg = candidate.config or {}
        if candidate.kind == "youtube_data":
            return bool(settings.youtube_research_api_key or os.getenv("YOUTUBE_RESEARCH_API_KEY", ""))
        if candidate.kind == "openai_compatible":
            key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key", ""))
            return bool((cfg.get("base_url") or settings.llm_base_url) and (key or settings.llm_api_key) and (cfg.get("model") or settings.llm_model))
        if candidate.kind == "stability_image":
            return bool(settings.stability_api_key or os.getenv("STABILITY_API_KEY", ""))
        if candidate.kind == "pexels_photo" or candidate.kind == "pexels_video":
            return bool(settings.pexels_api_key or os.getenv("PEXELS_API_KEY", ""))
        if candidate.kind == "openai_image":
            key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key", "") or settings.image_api_key or settings.llm_api_key)
            return bool((cfg.get("base_url") or cfg.get("endpoint") or settings.image_endpoint or "https://api.openai.com/v1") and (key or settings.image_api_key or settings.llm_api_key) and (cfg.get("model") or settings.image_model or "gpt-image-2"))
        if candidate.kind == "runway":
            return bool(settings.runway_api_key or settings.video_api_key or os.getenv("RUNWAY_API_KEY", "") or os.getenv("RUNWAYML_API_SECRET", "") or os.getenv("RUNWAY_API_SECRET", "") or os.getenv("RUNWAY_API", ""))
        if candidate.kind == "openai_tts":
            key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key", "") or settings.tts_api_key or settings.llm_api_key)
            return bool((cfg.get("base_url") or cfg.get("endpoint") or settings.tts_endpoint or "https://api.openai.com/v1") and (key or settings.tts_api_key or settings.llm_api_key) and (cfg.get("model") or settings.tts_model or "gpt-4o-mini-tts"))
        if candidate.kind == "elevenlabs":
            return bool((settings.elevenlabs_api_key or settings.tts_api_key or os.getenv("ELEVENLABS_API_KEY", "")) and (settings.elevenlabs_voice_id or settings.tts_voice))
        if candidate.kind in {"http_json", "http_image", "http_video"}:
            endpoint_defaults = {
                "http_json": settings.research_endpoint,
                "http_image": settings.image_endpoint or settings.visual_endpoint,
                "http_video": settings.video_endpoint,
            }
            key_defaults = {
                "http_json": settings.research_api_key,
                "http_image": settings.image_api_key or settings.visual_api_key,
                "http_video": settings.video_api_key,
            }
            key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key", ""))
            return bool(cfg.get("endpoint") or endpoint_defaults[candidate.kind]) and (key or key_defaults[candidate.kind] or not cfg.get("requires_api_key", False))
        return False

    async def candidates(self, portfolio_id, service: str) -> list[Candidate]:
        rows = (await self.db.execute(
            select(ProviderProfile).where(
                ProviderProfile.portfolio_id == portfolio_id,
                ProviderProfile.service == service,
                ProviderProfile.enabled.is_(True),
            ).order_by(ProviderProfile.priority.desc(), ProviderProfile.unit_cost_usd.asc())
        )).scalars().all()
        if rows:
            configured = SETTINGS_PROVIDER.get(service, lambda: "mock")()
            result = [Candidate(
                provider=r.provider, kind=r.kind, tier=r.quality_tier, priority=r.priority,
                unit=r.unit, unit_cost_usd=r.unit_cost_usd, capabilities=r.capabilities or {},
                config=r.config_json or {}, runtime_available=self._runtime_available(Candidate(
                    provider=r.provider, kind=r.kind, tier=r.quality_tier, priority=r.priority,
                    unit=r.unit, unit_cost_usd=r.unit_cost_usd, capabilities=r.capabilities or {}, config=r.config_json or {},
                )),
            ) for r in rows]
            fallback_spec = DEFAULTS.get(service, [None])[0]
            if fallback_spec and not any(c.provider == fallback_spec["provider"] and c.runtime_available for c in result):
                result.append(
                    Candidate(
                        **{**fallback_spec, "config": {}},
                        runtime_available=self._runtime_available(
                            Candidate(**{**fallback_spec, "config": {}})
                        ),
                    )
                )
            return result
        configured = SETTINGS_PROVIDER.get(service, lambda: "mock")()
        specs = []
        for spec in DEFAULTS.get(service, []):
            if spec["provider"] == configured or spec["provider"] == "mock":
                specs.append(spec)
        if configured and not any(x["provider"] == configured for x in specs):
            specs.append({"provider": configured, "kind": configured, "tier": "standard", "priority": 80, "unit": "request", "unit_cost_usd": 0.0, "capabilities": {}})
        result: list[Candidate] = []
        for spec in specs:
            candidate = Candidate(
                provider=spec["provider"], kind=spec["kind"], tier=spec["tier"], priority=spec["priority"],
                unit=spec["unit"], unit_cost_usd=spec["unit_cost_usd"], capabilities=spec.get("capabilities", {}), config=spec.get("config", {}),
            )
            result.append(Candidate(**{**asdict(candidate), "runtime_available": self._runtime_available(candidate)}))
        return result

    async def _spend(self, portfolio_id, *, provider: str | None = None, service: str | None = None, channel_id=None, since: datetime | None = None) -> float:
        stmt = select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(CostEvent.portfolio_id == portfolio_id)
        if provider:
            stmt = stmt.where(CostEvent.provider == provider)
        if service:
            stmt = stmt.where(CostEvent.service == service)
        if channel_id:
            stmt = stmt.where(CostEvent.channel_id == channel_id)
        if since:
            stmt = stmt.where(CostEvent.created_at >= since)
        return float(await self.db.scalar(stmt) or 0.0)

    async def _feasible(self, portfolio: Portfolio, candidate: Candidate, service: str, estimated: float, channel_id=None) -> tuple[bool, list[str]]:
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        day_start = datetime(now.year, now.month, now.day)
        reasons: list[str] = []
        portfolio_month = await self._spend(portfolio.id, since=month_start)
        portfolio_day = await self._spend(portfolio.id, since=day_start)
        if portfolio.monthly_budget_usd > 0 and portfolio_month + estimated > portfolio.monthly_budget_usd:
            reasons.append("portfolio_monthly_budget")
        if portfolio.daily_budget_usd > 0 and portfolio_day + estimated > portfolio.daily_budget_usd:
            reasons.append("portfolio_daily_budget")

        budget = await self.db.scalar(select(ProviderBudget).where(
            ProviderBudget.portfolio_id == portfolio.id,
            ProviderBudget.provider == candidate.provider,
            ProviderBudget.service == service,
        ))
        if budget:
            provider_month = await self._spend(portfolio.id, provider=candidate.provider, service=service, since=month_start)
            provider_day = await self._spend(portfolio.id, provider=candidate.provider, service=service, since=day_start)
            if budget.monthly_limit_usd > 0 and provider_month + estimated > budget.monthly_limit_usd and budget.hard_limit:
                reasons.append("provider_monthly_hard_limit")
            if budget.daily_limit_usd > 0 and provider_day + estimated > budget.daily_limit_usd and budget.hard_limit:
                reasons.append("provider_daily_hard_limit")

        if channel_id:
            link = await self.db.scalar(select(PortfolioChannel).where(
                PortfolioChannel.portfolio_id == portfolio.id,
                PortfolioChannel.channel_id == channel_id,
                PortfolioChannel.active.is_(True),
            ))
            if link and link.monthly_budget_usd > 0:
                channel_month = await self._spend(portfolio.id, channel_id=channel_id, since=month_start)
                if channel_month + estimated > link.monthly_budget_usd:
                    reasons.append("channel_monthly_budget")
        return not reasons, reasons

    async def route(
        self,
        *,
        owner_id: str = "local-user",
        service: str,
        requested_tier: str = "standard",
        units: float = 1.0,
        channel_id=None,
        project_id=None,
        step_name: str = "unknown",
        required_capabilities: Iterable[str] | None = None,
        allow_quality_downgrade: bool = True,
        exclude_providers: set[str] | None = None,
    ) -> dict[str, Any]:
        if requested_tier not in TIER_ORDER:
            requested_tier = "standard"
        portfolio = await self.ensure_portfolio(owner_id)
        candidates = await self.candidates(portfolio.id, service)
        required = set(required_capabilities or [])
        excluded = exclude_providers or set()
        reliability = ProviderReliabilityService(self.db)
        feasible: dict[str, bool] = {}
        details: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            capability_ok = required.issubset(set((candidate.capabilities or {}).keys()))
            if candidate.provider in excluded:
                feasible[candidate.provider] = False
                details[candidate.provider] = {
                    "capability_ok": capability_ok, "runtime_available": candidate.runtime_available,
                    "affordable": False, "budget_reasons": ["excluded_after_previous_failure"],
                    "estimated_cost_usd": candidate.estimate(units),
                }
                continue
            affordable, reasons = await self._feasible(portfolio, candidate, service, candidate.estimate(units), channel_id)
            circuit_ok = await reliability.can_route(portfolio.id, service, candidate.provider)
            if not circuit_ok:
                reasons = [*reasons, "provider_circuit_open"]
            feasible[candidate.provider] = capability_ok and affordable and candidate.runtime_available and circuit_ok
            details[candidate.provider] = {
                "capability_ok": capability_ok,
                "runtime_available": candidate.runtime_available,
                "circuit_ok": circuit_ok,
                "affordable": affordable,
                "budget_reasons": reasons,
                "estimated_cost_usd": candidate.estimate(units),
            }
        ordered = rank_candidates(
            candidates, requested_tier=requested_tier, units=units,
            feasible=feasible, allow_quality_downgrade=allow_quality_downgrade,
        )
        chosen = next((c for c in ordered if feasible.get(c.provider)), None)
        if chosen is None:
            raise ValueError(f"No feasible provider for service={service}")
        first = ordered[0] if ordered else chosen
        fallback_used = chosen.provider != first.provider or chosen.tier_rank < TIER_ORDER[requested_tier]
        reason = f"selected={chosen.provider}; tier={chosen.tier}; cost={chosen.estimate(units):.8f} USD"
        if fallback_used:
            reason += "; fallback/quality-downgrade path used"
        candidate_payload = []
        for c in candidates:
            candidate_payload.append({
                "provider": c.provider, "tier": c.tier, "priority": c.priority,
                "unit": c.unit, "unit_cost_usd": c.unit_cost_usd,
                **details[c.provider],
            })
        record = RoutingDecision(
            owner_id=owner_id, portfolio_id=portfolio.id, channel_id=channel_id, project_id=project_id,
            step_name=step_name, service=service, requested_tier=requested_tier,
            chosen_provider=chosen.provider, chosen_tier=chosen.tier, fallback_used=fallback_used,
            estimated_cost_usd=chosen.estimate(units), reason=reason, candidates_json=candidate_payload,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return {
            "decision_id": str(record.id), "service": service, "requested_tier": requested_tier,
            "provider": chosen.provider, "kind": chosen.kind, "tier": chosen.tier,
            "estimated_cost_usd": chosen.estimate(units), "fallback_used": fallback_used,
            "reason": reason, "config": chosen.config, "candidates": candidate_payload,
        }

    async def project_plan(self, *, owner_id: str, channel_id, project_id, goal: str = "balanced", quality_mode: str = "balanced") -> dict[str, dict[str, Any]]:
        requested = {"cost": "economy", "balanced": "standard", "quality": "premium", "premium": "premium"}.get(quality_mode, "standard")
        if goal == "authority" and quality_mode != "cost":
            requested = "premium"
        tasks = [
            ("research", "research", 1, {"search"}),
            ("research_llm", "llm", 1, {"json"}),
            ("script", "llm", 1, {"json"}),
            ("storyboard", "llm", 1, {"json"}),
            ("scene_director", "llm", 1, {"json"}),
            ("production", "visual", 5, {"image", "generative"}),
            ("production_video", "video", 5, {"video", "generative"}),
            ("tts", "tts", 1, {"voice"}),
            ("editor", "render", 1, {"render"}),
            ("thumbnail", "image", 1, {"image", "generative"}),
            ("qa", "llm", 1, {"json"}),
        ]
        plan: dict[str, dict[str, Any]] = {}
        for step, service, units, caps in tasks:
            plan[step] = await self.route(
                owner_id=owner_id, service=service, requested_tier=requested,
                units=units, channel_id=channel_id, project_id=project_id,
                step_name=step, required_capabilities=caps,
            )
        return plan

    async def configure_profile(
        self, owner_id: str, *, provider: str, service: str, kind: str, quality_tier: str,
        priority: int, unit: str, unit_cost_usd: float, capabilities: dict[str, Any], config_json: dict[str, Any], enabled: bool = True,
    ) -> ProviderProfile:
        portfolio = await self.ensure_portfolio(owner_id)
        row = await self.db.scalar(select(ProviderProfile).where(
            ProviderProfile.portfolio_id == portfolio.id, ProviderProfile.provider == provider, ProviderProfile.service == service,
        ))
        if not row:
            row = ProviderProfile(portfolio_id=portfolio.id, provider=provider, service=service)
            self.db.add(row)
        row.kind = kind
        row.quality_tier = quality_tier
        row.priority = priority
        row.unit = unit
        row.unit_cost_usd = max(0.0, unit_cost_usd)
        row.capabilities = capabilities or {}
        row.config_json = config_json or {}
        row.enabled = enabled
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def profiles(self, owner_id: str = "local-user") -> list[ProviderProfile]:
        portfolio = await self.ensure_portfolio(owner_id)
        result = await self.db.execute(select(ProviderProfile).where(ProviderProfile.portfolio_id == portfolio.id).order_by(ProviderProfile.service, ProviderProfile.priority.desc()))
        return list(result.scalars().all())

    async def decisions(self, owner_id: str = "local-user", limit: int = 100) -> list[RoutingDecision]:
        portfolio = await self.ensure_portfolio(owner_id)
        result = await self.db.execute(select(RoutingDecision).where(RoutingDecision.portfolio_id == portfolio.id).order_by(RoutingDecision.created_at.desc()).limit(limit))
        return list(result.scalars().all())
