from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Any
import uuid

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PostPublishMonitor, PerformanceAlert, AnalyticsSnapshot, VideoProject, Channel
from app.autonomous_optimization import AutonomousOptimizationService


class PostPublishMonitorService:
    """Poll published videos and detect explainable performance anomalies."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, organization_id, portfolio_id, channel_id, video_id: str, project_id=None,
                     interval_minutes: int = 60, baseline_days: int = 28, anomaly_threshold_pct: float = 20.0,
                     auto_correct: bool = False, first_check_at: datetime | None = None) -> PostPublishMonitor:
        if interval_minutes < 5 or interval_minutes > 1440:
            raise ValueError("interval_minutes must be between 5 and 1440")
        if baseline_days < 7 or baseline_days > 90:
            raise ValueError("baseline_days must be between 7 and 90")
        if anomaly_threshold_pct < 5 or anomaly_threshold_pct > 80:
            raise ValueError("anomaly_threshold_pct must be between 5 and 80")
        existing = await self.db.scalar(select(PostPublishMonitor).where(PostPublishMonitor.channel_id == channel_id, PostPublishMonitor.youtube_video_id == video_id))
        if existing:
            existing.enabled = True
            existing.interval_minutes = interval_minutes
            existing.baseline_days = baseline_days
            existing.anomaly_threshold_pct = anomaly_threshold_pct
            existing.auto_correct = auto_correct
            existing.next_check_at = min(existing.next_check_at, datetime.utcnow())
            await self.db.commit()
            return existing
        row = PostPublishMonitor(
            organization_id=organization_id,
            portfolio_id=portfolio_id,
            channel_id=channel_id,
            project_id=project_id,
            youtube_video_id=video_id,
            interval_minutes=interval_minutes,
            baseline_days=baseline_days,
            anomaly_threshold_pct=anomaly_threshold_pct,
            auto_correct=auto_correct,
            next_check_at=first_check_at or datetime.utcnow(),
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def process_due(self, limit: int = 10) -> int:
        now = datetime.utcnow()
        q = await self.db.execute(
            select(PostPublishMonitor)
            .where(PostPublishMonitor.enabled.is_(True), PostPublishMonitor.next_check_at <= now)
            .order_by(PostPublishMonitor.next_check_at.asc())
            .with_for_update(skip_locked=True)
            .limit(max(1, min(limit, 50)))
        )
        monitors = list(q.scalars().all())
        if not monitors:
            return 0
        for monitor in monitors:
            monitor.next_check_at = now + timedelta(minutes=monitor.interval_minutes)
            monitor.last_checked_at = now
            monitor.checks_count += 1
        await self.db.commit()
        processed = 0
        for monitor in monitors:
            try:
                await self.check_one(monitor.id)
                processed += 1
            except Exception as exc:
                await self._mark_monitor_error(monitor.id, str(exc))
        return processed

    async def check_one(self, monitor_id) -> dict[str, Any]:
        monitor = await self.db.get(PostPublishMonitor, monitor_id, with_for_update=True)
        if not monitor:
            raise ValueError("monitor not found")
        from app.services.youtube_service import analytics as youtube_analytics
        from app.schemas.youtube import AnalyticsRequest
        end = datetime.utcnow().date()
        start = end - timedelta(days=min(max(monitor.baseline_days, 7), 28))
        # Re-use the existing YouTube integration. It persists the daily rows for future checks.
        await youtube_analytics(self.db, str(monitor.channel_id), AnalyticsRequest(
            start_date=start.isoformat(), end_date=end.isoformat(), video_id=monitor.youtube_video_id,
        ))
        latest = await self.db.scalar(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.channel_id == monitor.channel_id, AnalyticsSnapshot.youtube_video_id == monitor.youtube_video_id)
            .order_by(AnalyticsSnapshot.day.desc()).limit(1)
        )
        if not latest:
            monitor.last_status = "NO_DATA"
            await self.db.commit()
            return {"status": "NO_DATA"}

        history_q = await self.db.execute(
            select(AnalyticsSnapshot)
            .where(
                AnalyticsSnapshot.channel_id == monitor.channel_id,
                AnalyticsSnapshot.youtube_video_id != monitor.youtube_video_id,
                AnalyticsSnapshot.day >= start,
                AnalyticsSnapshot.day <= end,
            )
        )
        history = list(history_q.scalars().all())
        baseline = self._baseline(history)
        anomalies = self._detect(latest, baseline, float(monitor.anomaly_threshold_pct))

        await self._record_learning_feedback(monitor, latest, baseline)

        corrective: dict[str, Any] = {}
        optimization_decisions: list[dict[str, Any]] = []
        for metric, anomaly in anomalies.items():
            dedupe_key = f"{monitor.id}:{metric}"
            await self._upsert_alert(monitor, metric, anomaly, dedupe_key)
            alert = await self.db.scalar(select(PerformanceAlert).where(PerformanceAlert.dedupe_key == dedupe_key))
            if alert and monitor.project_id:
                project = await self.db.get(VideoProject, monitor.project_id)
                channel = await self.db.get(Channel, monitor.channel_id)
                if project and channel:
                    decision = await AutonomousOptimizationService(self.db).decide(project=project, channel=channel, alert=alert)
                    optimization_decisions.append({"metric": metric, "decision_id": str(decision.id), "target_scope": decision.target_scope, "priority": decision.priority, "confidence": decision.confidence})
        if anomalies and monitor.auto_correct and monitor.project_id:
            corrective = await self._create_corrective_experiment(monitor, anomalies)
            if corrective:
                for metric in anomalies:
                    alert = await self.db.scalar(select(PerformanceAlert).where(PerformanceAlert.dedupe_key == f"{monitor.id}:{metric}").with_for_update())
                    if alert:
                        alert.remediation = {**(alert.remediation or {}), **corrective}
        await self._resolve_recovered(monitor, anomalies)

        monitor.last_status = "ANOMALY" if anomalies else "HEALTHY"
        await self.db.commit()
        return {"status": monitor.last_status, "video_id": monitor.youtube_video_id, "baseline": baseline, "anomalies": anomalies, "optimization_decisions": optimization_decisions}

    async def _record_learning_feedback(self, monitor: PostPublishMonitor, latest: AnalyticsSnapshot, baseline: dict[str, float]) -> None:
        if not monitor.project_id or not latest.youtube_video_id:
            return
        from app.models import AgentTask
        task = await self.db.scalar(
            select(AgentTask)
            .where(
                AgentTask.channel_id == monitor.channel_id,
                AgentTask.project_id == monitor.project_id,
                AgentTask.agent_key == "publisher",
                AgentTask.action_type == "publish",
                AgentTask.status == "SUCCEEDED",
            )
            .order_by(AgentTask.completed_at.desc())
        )
        if not task:
            return
        from app.learning.service import AgentLearningService
        await AgentLearningService(self.db).record_post_publish_feedback(
            task=task,
            youtube_video_id=latest.youtube_video_id,
            metrics={
                "day": latest.day.isoformat(),
                "views": latest.views,
                "average_view_percentage": latest.average_view_percentage,
                "impression_ctr": latest.impression_ctr,
                "likes": latest.likes,
                "comments": latest.comments,
                "shares": latest.shares,
                "subscribers_gained": latest.subscribers_gained,
                "subscribers_lost": latest.subscribers_lost,
            },
            baseline=baseline,
            source_key=latest.day.isoformat(),
        )

    @staticmethod
    def _baseline(rows: list[AnalyticsSnapshot]) -> dict[str, float]:
        if not rows:
            return {"views": 0.0, "average_view_percentage": 0.0, "impression_ctr": 0.0}
        def med(name: str) -> float:
            values = [float(getattr(row, name, 0) or 0) for row in rows if float(getattr(row, name, 0) or 0) > 0]
            return float(median(values)) if values else 0.0
        return {"views": med("views"), "average_view_percentage": med("average_view_percentage"), "impression_ctr": med("impression_ctr")}

    @staticmethod
    def _detect(latest: AnalyticsSnapshot, baseline: dict[str, float], threshold_pct: float) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        configs = (
            ("views", "views", 1.5),
            ("retention", "average_view_percentage", 1.0),
            ("ctr", "impression_ctr", 1.0),
        )
        for alert_type, attr, multiplier in configs:
            current = float(getattr(latest, attr, 0) or 0)
            base = float(baseline.get(attr, 0) or 0)
            if current <= 0 or base <= 0:
                continue
            delta_pct = (current / base - 1.0) * 100
            required = threshold_pct * multiplier
            if delta_pct <= -required:
                severity = "high" if delta_pct <= -max(40.0, threshold_pct * 2) else "medium"
                result[alert_type] = {
                    "metric": attr,
                    "current_value": round(current, 4),
                    "baseline_value": round(base, 4),
                    "delta_pct": round(delta_pct, 2),
                    "severity": severity,
                    "reason": f"{attr} is {abs(delta_pct):.1f}% below observed channel baseline",
                }
        return result

    async def _upsert_alert(self, monitor: PostPublishMonitor, metric: str, anomaly: dict[str, Any], dedupe_key: str) -> None:
        existing = await self.db.scalar(select(PerformanceAlert).where(PerformanceAlert.dedupe_key == dedupe_key).with_for_update())
        if existing:
            existing.current_value = anomaly["current_value"]
            existing.baseline_value = anomaly["baseline_value"]
            existing.delta_pct = anomaly["delta_pct"]
            existing.severity = anomaly["severity"]
            existing.evidence = {"reason": anomaly["reason"], "checked_at": datetime.utcnow().isoformat()}
            existing.status = "OPEN"
            existing.resolved_at = None
            existing.remediation = self._remediation(metric, monitor.auto_correct)
            return
        alert = PerformanceAlert(
            monitor_id=monitor.id,
            organization_id=monitor.organization_id,
            channel_id=monitor.channel_id,
            youtube_video_id=monitor.youtube_video_id,
            dedupe_key=dedupe_key,
            alert_type=f"post_publish_{metric}",
            severity=anomaly["severity"],
            metric=anomaly["metric"],
            current_value=anomaly["current_value"],
            baseline_value=anomaly["baseline_value"],
            delta_pct=anomaly["delta_pct"],
            evidence={"reason": anomaly["reason"], "checked_at": datetime.utcnow().isoformat()},
            remediation=self._remediation(metric, monitor.auto_correct),
        )
        self.db.add(alert)

    async def _resolve_recovered(self, monitor: PostPublishMonitor, anomalies: dict[str, Any]) -> None:
        q = await self.db.execute(select(PerformanceAlert).where(PerformanceAlert.monitor_id == monitor.id, PerformanceAlert.status == "OPEN"))
        for alert in q.scalars().all():
            key = alert.dedupe_key.rsplit(":", 1)[-1]
            if key not in anomalies:
                alert.status = "RESOLVED"
                alert.resolved_at = datetime.utcnow()

    async def _create_corrective_experiment(self, monitor: PostPublishMonitor, anomalies: dict[str, Any]) -> dict[str, Any]:
        from app.models.experiments import ContentExperiment
        from app.brain.service import optimize_video
        from app.experiments.engine import ExperimentEngine

        q = await self.db.execute(select(ContentExperiment).where(
            ContentExperiment.video_project_id == monitor.project_id,
            ContentExperiment.status.in_({"DRAFT", "RUNNING"}),
        ))
        existing = list(q.scalars().all())
        try:
            result = await optimize_video(self.db, str(monitor.channel_id), monitor.youtube_video_id)
            report_id = result.get("report_id")
            if not report_id:
                return {}
            from app.models.optimization import OptimizationReport
            opt_report = await self.db.get(OptimizationReport, uuid.UUID(report_id))
            if not opt_report:
                return {}
            from app.models.domain import VideoProject
            project = await self.db.get(VideoProject, monitor.project_id) if monitor.project_id else None
            spec = ExperimentEngine().build_from_optimization(report=opt_report, project=project)
            same_dimension = next((e for e in existing if e.dimension == spec["dimension"]), None)
            if same_dimension:
                return {"optimization_report_id": report_id, "existing_experiment_id": str(same_dimension.id), "auto_corrected": False}
            created = await ExperimentEngine().create_from_report(self.db, channel_id=str(monitor.channel_id), report_id=report_id)
            return {"optimization_report_id": report_id, "experiment_id": str(created.id), "auto_corrected": True}
        except Exception:
            return {}


    async def _mark_monitor_error(self, monitor_id, error: str) -> None:
        monitor = await self.db.get(PostPublishMonitor, monitor_id)
        if monitor:
            monitor.last_status = "ERROR"
            monitor.metadata_json = {**(monitor.metadata_json or {}), "last_error": str(error)[:1000]}
            await self.db.commit()

    @staticmethod
    def _remediation(metric: str, auto_correct: bool) -> dict[str, Any]:
        action = {
            "views": "review_topic_and_packaging",
            "retention": "review_opening_and_pacing",
            "ctr": "review_title_and_thumbnail",
        }.get(metric, "review_video")
        return {"action": action, "auto_correct_requested": bool(auto_correct), "guardrail": "do_not_modify_published_video_without_explicit experiment_policy"}
