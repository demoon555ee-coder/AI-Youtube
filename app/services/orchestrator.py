from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VideoProject, Channel, AgentRun, ChannelMemory, WorkflowRun, WorkflowStep, WorkflowEvent, RoutingDecision, MediaGenerationJob, ContentVersion
from app.agents.factory import build_agent
from app.routing import ProviderRouter
from app.rendering.service import RenderService
from app.thumbnail import ThumbnailFactory
from app.portfolio.service import PortfolioService
from app.config import settings
from app.quality.service import VideoQualityService
from app.resilience.provider import ProviderReliabilityService, is_transient_provider_error
from app.evolution.service import ContentEvolutionService
from app.multimodal_graph.service import MultimodalProductionGraphService


class Orchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.router = ProviderRouter(db)
        self.renderer = RenderService(settings.output_dir)
        self.thumbnails = ThumbnailFactory(settings.output_dir)

    async def run_project(self, project_id: str, workflow_id: str | None = None):
        project = await self.db.get(VideoProject, project_id)
        if not project:
            raise ValueError("Project not found")
        channel = await self.db.get(Channel, project.channel_id)
        if not channel:
            raise ValueError("Channel not found")

        workflow = None
        if workflow_id:
            workflow = await self.db.get(WorkflowRun, workflow_id)
            if not workflow or workflow.project_id != project.id:
                raise ValueError("Workflow not found for project")

        memory_row = await self.db.get(ChannelMemory, channel.id)
        channel_memory = {
            "version": memory_row.version if memory_row else 0,
            "summary": memory_row.summary if memory_row else "",
            "learned_patterns": memory_row.learned_patterns if memory_row else [],
            "topic_clusters": memory_row.topic_clusters if memory_row else [],
            "hook_patterns": memory_row.hook_patterns if memory_row else [],
            "title_patterns": memory_row.title_patterns if memory_row else [],
            "pacing_patterns": memory_row.pacing_patterns if memory_row else [],
        }
        project_data = dict(project.data or {})
        evolution = project_data.get("evolution") or {}
        if evolution.get("execution_mode") == "targeted_scene_reedit":
            return await self._run_targeted_execution(project, channel, workflow, evolution)
        version_row = await self.db.scalar(select(ContentVersion).where(ContentVersion.project_id == project.id).with_for_update())
        if version_row:
            version_row.status = "IN_PROGRESS"
            version_row.updated_at = datetime.utcnow()
            await self.db.flush()
        owner_id = channel.owner_id
        portfolio = await PortfolioService(self.db).ensure(owner_id)
        quality_mode = project_data.get("quality_mode", "balanced")
        goal = project_data.get("goal") or project_data.get("strategy", {}).get("goal", "balanced")
        try:
            routing_plan = dict(project_data.get("routing_plan") or {})
            requested_steps = ["research", "script", "storyboard", "scene_director", "production", "editor", "thumbnail", "qa"]
            completed_keys: set[str] = set()
            if workflow:
                existing_step_rows = (await self.db.execute(
                    select(WorkflowStep).where(WorkflowStep.workflow_run_id == workflow.id)
                )).scalars().all()
                completed_keys = {row.step_key for row in existing_step_rows if row.status == "COMPLETED"}
            requested_steps = [step for step in requested_steps if step not in completed_keys]

            # Route each unfinished step independently. A step that failed on its previous
            # attempt excludes its last provider so a transient outage can trigger a real fallback.
            for step_name in requested_steps:
                previous_provider = None
                latest_decision = await self.db.scalar(
                    select(RoutingDecision).where(
                        RoutingDecision.project_id == project.id, RoutingDecision.step_name == step_name
                    ).order_by(RoutingDecision.created_at.desc()).limit(1)
                )
                latest_run = await self._latest_step_run(project.id, step_name)
                if latest_run and latest_run.status == "FAILED" and latest_decision:
                    previous_provider = latest_decision.chosen_provider
                service_by_step = {
                    "research": "research", "script": "llm", "storyboard": "llm", "scene_director": "llm",
                    "production": "visual", "editor": "render", "thumbnail": "image", "qa": "llm",
                }
                caps_by_step = {
                    "research": {"search"}, "script": {"json"}, "storyboard": {"json"}, "scene_director": {"json"},
                    "production": {"image"}, "editor": {"render"}, "thumbnail": {"image"}, "qa": {"json"},
                }
                units_by_step = {"research": 1, "script": 1, "storyboard": 1, "scene_director": 1, "production": 5, "editor": 1, "thumbnail": 1, "qa": 1}
                requested_tier = {"cost": "economy", "balanced": "standard", "quality": "premium", "premium": "premium"}.get(quality_mode, "standard")
                if goal == "authority" and quality_mode != "cost":
                    requested_tier = "premium"
                route_meta = await self.router.route(
                    owner_id=owner_id, service=service_by_step[step_name], requested_tier=requested_tier,
                    units=units_by_step[step_name], channel_id=channel.id, project_id=project.id,
                    step_name=step_name, required_capabilities=caps_by_step[step_name],
                    exclude_providers={previous_provider} if previous_provider else None,
                )
                routing_plan[step_name] = route_meta
            auxiliary = [
                ("research_llm", "llm", {"json"}, 1),
                ("production_video", "video", {"video"}, 5),
                ("tts", "tts", {"voice"}, 1),
            ]
            for route_name, service_name, caps, units in auxiliary:
                if route_name in routing_plan:
                    continue
                route_meta = await self.router.route(
                    owner_id=owner_id, service=service_name, requested_tier=requested_tier, units=units,
                    channel_id=channel.id, project_id=project.id, step_name=route_name, required_capabilities=caps,
                )
                routing_plan[route_name] = route_meta
            project_data["routing_plan"] = routing_plan
            await self.db.commit()
        except Exception:
            # Routing is a hard production dependency; surface budget/provider errors instead
            # of silently selecting an untracked provider.
            await self.db.rollback()
            raise
        context = {
            "project_id": str(project.id),
            "topic": project.topic,
            "channel": {
                "name": channel.name,
                "niche": channel.niche,
                "language": channel.language,
                "memory": channel_memory,
            },
            "idea_context": {
                "title": project_data.get("title"),
                "hook": project_data.get("hook"),
                "angle": project_data.get("angle"),
                "strategy": project_data.get("strategy", {}),
                "content_intelligence": project_data.get("content_intelligence", {}),
                "evolution": evolution,
            },
            "content_intelligence": project_data.get("content_intelligence", {}),
        }

        if workflow:
            step_rows = await self.db.execute(
                select(WorkflowStep).where(WorkflowStep.workflow_run_id == workflow.id).order_by(WorkflowStep.step_order)
            )
            steps_rows = list(step_rows.scalars().all())
            if len(steps_rows) == 7:
                # Upgrade an old v1.0 workflow in-place by inserting the v1.1 Scene Director step.
                production_step = next((row for row in steps_rows if row.step_key == "production"), None)
                if production_step:
                    from app.models.workflow import WorkflowStep as WorkflowStepModel
                    for row in steps_rows:
                        if row.step_order >= production_step.step_order:
                            row.step_order += 1
                    new_step = WorkflowStepModel(
                        workflow_run_id=workflow.id, step_key="scene_director", step_order=production_step.step_order
                    )
                    self.db.add(new_step)
                    await self.db.commit()
                    step_rows = await self.db.execute(
                        select(WorkflowStep).where(WorkflowStep.workflow_run_id == workflow.id).order_by(WorkflowStep.step_order)
                    )
                    steps_rows = list(step_rows.scalars().all())
        else:
            steps_rows = [None] * 8

        steps = [
            ("research", "RESEARCHING"),
            ("script", "SCRIPTING"),
            ("storyboard", "STORYBOARDING"),
            ("scene_director", "DIRECTING_SCENES"),
            ("production", "GENERATING_ASSETS"),
            ("editor", "EDITING"),
            ("thumbnail", "GENERATING_THUMBNAIL"),
            ("qa", "QA"),
        ]

        for index, (name, status) in enumerate(steps):
            if workflow:
                await self.db.refresh(workflow)
                if workflow.status == "CANCELLED":
                    raise RuntimeError("Workflow cancelled")
            step = steps_rows[index] if workflow else None
            if step and step.status == "COMPLETED":
                context[name] = step.output_data or project_data.get(name, {}) or {}
                continue

            project.status = status
            if workflow:
                workflow.current_step = name
                step.status = "RUNNING"
                step.attempts += 1
                step.started_at = step.started_at or datetime.utcnow()
            await self.db.commit()
            await self._event(workflow, project, "step.started", {"step": name, "attempt": step.attempts if step else 1})

            run = await self._latest_step_run(project.id, name)
            if run and run.status == "RUNNING":
                # Recover an interrupted agent run by starting a fresh run record.
                run.status = "ABANDONED"
                run.finished_at = datetime.utcnow()
                await self.db.commit()

            run = AgentRun(
                project_id=project.id,
                agent_name=name,
                input_data=context,
            )
            self.db.add(run)
            await self.db.commit()
            await self.db.refresh(run)

            try:
                if name == "qa":
                    quality = await VideoQualityService(self.db).evaluate(
                        project=project,
                        output=context.get("editor", {}),
                        stage="pre_publish",
                        organization_id=channel.organization_id,
                        portfolio_id=portfolio.id,
                    )
                    context["quality"] = quality
                    project.data = context
                    await self.db.flush()
                if name == "thumbnail":
                    route_meta = (project_data.get("routing_plan") or {}).get("thumbnail", {})
                    result = await self.thumbnails.create(
                        project_id=str(project.id),
                        title=context.get("script", {}).get("title") or project_data.get("title") or project.topic,
                        hook=context.get("script", {}).get("hook") or project_data.get("hook") or "",
                        provider_name=route_meta.get("provider") if route_meta.get("provider") != "mock_png" else None,
                        provider_config=route_meta.get("config") or {},
                    )
                elif name == "editor":
                    directed = context.get("scene_director") or context["storyboard"]
                    tts_route = (project_data.get("routing_plan") or {}).get("tts", {})
                    self.renderer = RenderService(settings.output_dir, tts_provider=tts_route.get("provider"), tts_config=tts_route.get("config") or {})
                    result = await self.renderer.render_video(
                        project_id=str(project.id),
                        storyboard=directed,
                        assets=context.get("production", {}).get("assets", []),
                        language=channel.language,
                    )
                    result["timeline"] = directed.get("scenes", [])
                    if settings.multimodal_graph_enabled:
                        preview_data = dict(context)
                        preview_data["editor"] = result
                        preview_data["production"] = context.get("production", {})
                        project.data = preview_data
                        try:
                            graph = await MultimodalProductionGraphService(self.db).analyze_rendered(
                                project=project, organization_id=channel.organization_id
                            )
                            result["multimodal_graph"] = graph
                        except Exception as exc:
                            # The post-render intelligence layer is observability; it cannot invalidate a successful render.
                            result["multimodal_graph_error"] = type(exc).__name__
                else:
                    route_meta = (project_data.get("routing_plan") or {}).get(name, {})
                    if name == "production":
                        if settings.multimodal_graph_enabled:
                            preflight = await MultimodalProductionGraphService(self.db).build_preflight(
                                project=project, organization_id=channel.organization_id
                            )
                            context["multimodal_preflight"] = preflight
                            project.data = context
                            if settings.multimodal_preflight_hard_fail and preflight.get("status") == "FAIL":
                                raise RuntimeError("Multimodal production preflight rejected: " + "; ".join(preflight.get("recommendations", [])[:4]))
                        video_route = (project_data.get("routing_plan") or {}).get("production_video", {})
                        prod_config = dict(route_meta.get("config") or {})
                        prod_config["image_provider"] = route_meta.get("provider")
                        prod_config["image_config"] = route_meta.get("config") or {}
                        prod_config["video_provider"] = video_route.get("provider")
                        prod_config["video_config"] = video_route.get("config") or {}
                        prod_config.update({"_db": self.db, "_organization_id": channel.organization_id, "_portfolio_id": portfolio.id, "_channel_id": channel.id, "_agent_run_id": run.id, "_workflow_attempt": workflow.attempt if workflow else 1})
                        agent = build_agent(name, provider=route_meta.get("provider"), config=prod_config)
                    elif name == "research":
                        llm_route = (project_data.get("routing_plan") or {}).get("research_llm", {})
                        research_config = dict(route_meta.get("config") or {})
                        research_config["llm_provider"] = llm_route.get("provider")
                        research_config["llm_config"] = llm_route.get("config") or {}
                        agent = build_agent(name, provider=route_meta.get("provider"), config=research_config)
                    else:
                        agent = build_agent(
                            name,
                            provider=route_meta.get("provider"),
                            config=route_meta.get("config") or {},
                        )
                    if agent is None:
                        raise RuntimeError(f"No agent implementation for {name}")
                    result = await agent.run(context)

                if name == "research":
                    from app.models.research import ResearchReport
                    external = result.get("external_research", {}) if isinstance(result, dict) else {}
                    external_results = external.get("results", []) if isinstance(external, dict) else []
                    self.db.add(ResearchReport(
                        channel_id=channel.id,
                        video_project_id=project.id,
                        query=project.topic,
                        sources=external_results,
                        competitor_findings=result.get("competitor_findings", []) if isinstance(result, dict) else [],
                        audience_findings=result.get("audience_questions", []) if isinstance(result, dict) else [],
                        content_gaps=result.get("content_gaps", []) if isinstance(result, dict) else [],
                        summary=result.get("source_summary", "") if isinstance(result, dict) else "",
                        provider=external.get("provider", "unknown") if isinstance(external, dict) else "unknown",
                    ))


                if name == "qa" and not result.get("approved", False):
                    raise RuntimeError("QA rejected video: " + "; ".join(result.get("issues", [])))

                context[name] = result
                project.data = context
                run.status = "COMPLETED"
                run.output_data = result
                run.finished_at = datetime.utcnow()
                if step:
                    step.status = "COMPLETED"
                    step.output_data = result
                    step.finished_at = datetime.utcnow()
                    step.error_message = None

                # Persist the completed step before cost metering. Metering is best effort;
                # a provider ledger problem must never roll back a successful production step.
                await self.db.commit()
                await self._event(workflow, project, "step.completed", {"step": name})
                await self._record_actual_usage(
                    channel=channel, project=project, run=run, step_name=name,
                    route_meta=(project_data.get("routing_plan") or {}).get(name, {}), result=result,
                    auxiliary_routes=(project_data.get("routing_plan") or {}),
                )
                await self._record_provider_successes(channel, project, name, result, project_data.get("routing_plan") or {})
            except Exception as exc:
                await self._record_provider_failure(channel, project, name, project_data.get("routing_plan") or {}, exc)
                run.status = "FAILED"
                run.error_message = str(exc)
                run.finished_at = datetime.utcnow()
                if step:
                    step.status = "FAILED" if step.attempts >= step.max_attempts else "PENDING"
                    step.error_message = str(exc)
                project.data = context
                version_row = await self.db.scalar(select(ContentVersion).where(ContentVersion.project_id == project.id).with_for_update())
                if version_row:
                    version_row.status = "FAILED"
                    version_row.updated_at = datetime.utcnow()
                await self.db.commit()
                await self._event(workflow, project, "step.failed", {"step": name, "error": str(exc)})
                raise

        project.data = context
        project.status = "READY_TO_PUBLISH"
        version_row = await self.db.scalar(select(ContentVersion).where(ContentVersion.project_id == project.id).with_for_update())
        if version_row:
            version_row.status = "READY_TO_PUBLISH"
            version_row.updated_at = datetime.utcnow()
        try:
            async with self.db.begin_nested():
                await ContentEvolutionService(self.db).register_project_artifacts(project)
        except Exception:
            # Artifact registry is integrity metadata; it must not make a successful render fail.
            pass
        await self.db.commit()
        if workflow:
            workflow.current_step = None
        await self.db.commit()
        await self._event(workflow, project, "project.ready_to_publish", {})
        return project

    async def _run_targeted_execution(self, project: VideoProject, channel: Channel, workflow: WorkflowRun | None, evolution: dict) -> VideoProject:
        from app.creative_intelligence.service import TargetedReEditService, CreativeIntelligenceService
        project_data = dict(project.data or {})
        parent = await self.db.get(VideoProject, project.parent_project_id) if project.parent_project_id else None
        if not parent:
            raise ValueError("Targeted execution source project not found")
        patches = evolution.get("scene_changes") or []
        if not patches:
            raise ValueError("Targeted execution has no scene changes")
        render = await TargetedReEditService(settings.output_dir).render_patch(
            source_project=parent, revision_project_id=str(project.id), scene_patches=patches
        )
        project.data = {**project_data, "editor": render}
        quality = await VideoQualityService(self.db).evaluate(project=project, output=render, stage="autonomous_targeted_reedit", organization_id=channel.organization_id)
        creative = await CreativeIntelligenceService(self.db).analyze(project=project, stage="autonomous_targeted_reedit", organization_id=channel.organization_id)
        project.data["qa"] = quality
        project.data["creative_intelligence"] = creative
        project.status = "READY_TO_PUBLISH" if quality.get("status") != "FAIL" else "FAILED"
        version_row = await self.db.scalar(select(ContentVersion).where(ContentVersion.project_id == project.id).with_for_update())
        if version_row:
            version_row.status = project.status
            version_row.updated_at = datetime.utcnow()
        if workflow:
            step_rows = list((await self.db.execute(select(WorkflowStep).where(WorkflowStep.workflow_run_id == workflow.id))).scalars().all())
            for step in step_rows:
                step.status = "COMPLETED" if project.status == "READY_TO_PUBLISH" else "FAILED"
                step.output_data = {"mode": "targeted_scene_reedit", "quality_status": quality.get("status")}
                step.finished_at = datetime.utcnow()
            workflow.current_step = None
        await self.db.commit()
        await self._event(workflow, project, "workflow.targeted_execution_completed", {"status": project.status, "patched_scenes": render.get("patched_scenes", [])})
        return project

    async def _record_provider_successes(self, channel, project, step_name: str, result: dict, routing_plan: dict) -> None:
        portfolio_id = (await PortfolioService(self.db).ensure(channel.owner_id)).id
        mapping = {
            "research": ("research", (routing_plan.get("research") or {}).get("provider")),
            "script": ("llm", (routing_plan.get("script") or {}).get("provider")),
            "storyboard": ("llm", (routing_plan.get("storyboard") or {}).get("provider")),
            "scene_director": ("llm", (routing_plan.get("scene_director") or {}).get("provider")),
            "editor": ("render", (routing_plan.get("editor") or {}).get("provider")),
            "thumbnail": ("image", (routing_plan.get("thumbnail") or {}).get("provider")),
            "qa": ("llm", (routing_plan.get("qa") or {}).get("provider")),
        }
        reliability = ProviderReliabilityService(self.db)
        if step_name in mapping and mapping[step_name][1]:
            await reliability.record_success(portfolio_id, mapping[step_name][0], mapping[step_name][1])
        if step_name == "production":
            assets = result.get("assets", []) if isinstance(result, dict) else []
            visual_provider = (routing_plan.get("production") or {}).get("provider")
            video_provider = (routing_plan.get("production_video") or {}).get("provider")
            if visual_provider:
                await reliability.record_success(portfolio_id, "visual", visual_provider)
            if any(str(a.get("asset_type", "")).lower() in {"video", "broll"} for a in assets) and video_provider:
                await reliability.record_success(portfolio_id, "video", video_provider)
            tts_provider = (routing_plan.get("tts") or {}).get("provider")
            if tts_provider:
                await reliability.record_success(portfolio_id, "tts", tts_provider)

    async def _record_provider_failure(self, channel, project, step_name: str, routing_plan: dict, exc: Exception) -> None:
        portfolio_id = (await PortfolioService(self.db).ensure(channel.owner_id)).id
        mapping = {
            "research": ("research", (routing_plan.get("research") or {}).get("provider")),
            "script": ("llm", (routing_plan.get("script") or {}).get("provider")),
            "storyboard": ("llm", (routing_plan.get("storyboard") or {}).get("provider")),
            "scene_director": ("llm", (routing_plan.get("scene_director") or {}).get("provider")),
            "production": ("visual", (routing_plan.get("production") or {}).get("provider")),
            "editor": ("render", (routing_plan.get("editor") or {}).get("provider")),
            "thumbnail": ("image", (routing_plan.get("thumbnail") or {}).get("provider")),
            "qa": ("llm", (routing_plan.get("qa") or {}).get("provider")),
        }
        item = mapping.get(step_name)
        if not item or not item[1] or str(item[1]).startswith("mock"):
            return
        if not is_transient_provider_error(exc):
            return
        reliability = ProviderReliabilityService(self.db)
        await reliability.record_failure(portfolio_id, item[0], item[1], str(exc))

    async def _record_actual_usage(
        self,
        *,
        channel,
        project,
        run,
        step_name: str,
        route_meta: dict,
        result: dict,
        auxiliary_routes: dict | None = None,
    ) -> None:
        """Best-effort provider cost ledger entry using configured route pricing.

        The workflow state is committed before this method runs. Any ledger failure is isolated
        so budget accounting can never roll back a successful media step.
        """
        if not channel.organization_id:
            return

        async def record(meta: dict, *, quantity: float, source: str, provider_usage: dict | None = None) -> None:
            provider = meta.get("provider")
            service = meta.get("service") or {
                "research": "research", "script": "llm", "storyboard": "llm", "scene_director": "llm",
                "production": "visual", "editor": "render", "thumbnail": "image", "qa": "llm",
            }.get(step_name, "general")
            unit = meta.get("unit") or "request"
            unit_cost = float(meta.get("unit_cost_usd") or 0.0)
            if not provider or unit_cost <= 0 or quantity <= 0:
                return
            try:
                await PortfolioService(self.db).record_cost(
                    channel.owner_id, provider=provider, service=service, unit=unit, quantity=quantity, unit_cost_usd=unit_cost,
                    channel_id=channel.id, project_id=project.id, agent_run_id=run.id,
                    metadata_json={"source": source, "provider_usage": provider_usage or {}},
                )
            except Exception:
                await self.db.rollback()

        if not route_meta:
            return

        usage = result.get("_provider_usage", {}) if isinstance(result, dict) else {}
        if step_name == "research":
            await record(route_meta, quantity=1.0, source="research.external", provider_usage=usage)
            research_llm_meta = (auxiliary_routes or {}).get("research_llm", {})
            await record(research_llm_meta, quantity=1.0, source="research.llm", provider_usage=usage)
            return

        if step_name == "production":
            assets = result.get("assets", []) if isinstance(result, dict) else []
            image_count = sum(1 for a in assets if str(a.get("asset_type", "image")).lower() not in {"video", "broll"})
            video_seconds = sum(float(a.get("duration_seconds") or 0.0) for a in assets if str(a.get("asset_type", "image")).lower() in {"video", "broll"})
            await record(route_meta, quantity=float(image_count), source="production.image", provider_usage=usage)
            video_meta = (auxiliary_routes or {}).get("production_video", {})
            await record(video_meta, quantity=float(video_seconds), source="production.video", provider_usage=usage)
            return

        if step_name == "editor":
            duration_seconds = float(result.get("duration_seconds") or 0.0)
            await record(route_meta, quantity=max(duration_seconds / 60.0, 0.01), source="editor.render", provider_usage=usage)
            tts_meta = (auxiliary_routes or {}).get("tts", {})
            await record(tts_meta, quantity=max(duration_seconds / 60.0, 0.01), source="editor.tts", provider_usage=usage)
            return

        await record(route_meta, quantity=1.0, source=step_name, provider_usage=usage)

    async def _latest_step_run(self, project_id, agent_name: str) -> AgentRun | None:
        q = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.project_id == project_id, AgentRun.agent_name == agent_name)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
        return q.scalar_one_or_none()

    async def _event(self, workflow: WorkflowRun | None, project: VideoProject, event_type: str, payload: dict) -> None:
        if not workflow:
            return
        self.db.add(WorkflowEvent(
            workflow_run_id=workflow.id,
            project_id=project.id,
            event_type=event_type,
            payload=payload,
        ))
        await self.db.commit()
