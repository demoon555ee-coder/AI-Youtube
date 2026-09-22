from __future__ import annotations

import asyncio
import base64
import json
import math
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ProductionMultimodalGraph, VideoProject
from app.quality.service import probe_media
from app.vision import get_vision_provider


class MultimodalProductionGraphService:
    """Builds one normalized graph across script, storyboard, media, audio, subtitles and timeline.

    The preflight graph is deliberately cheap and deterministic. The post-render graph augments
    it with actual media facts and a single multimodal vision pass over a contact sheet when the
    configured vision provider supports it. This lets the production workflow fail early or
    target specific scenes instead of blindly rerendering an entire project.
    """

    def __init__(self, db: AsyncSession | None = None, vision_provider=None, output_dir: str | None = None):
        self.db = db
        self.vision = vision_provider or get_vision_provider()
        self.output_dir = Path(output_dir or settings.output_dir).resolve()

    async def build_preflight(self, *, project: VideoProject, organization_id=None) -> dict[str, Any]:
        data = dict(project.data or {})
        script = data.get("script") or {}
        storyboard = data.get("scene_director") or data.get("storyboard") or {}
        scenes = list(storyboard.get("scenes") or [])
        graph = self._build_graph(
            project_id=project.id,
            stage="pre_render",
            script=script,
            scenes=scenes,
            production=data.get("production") or {},
            editor=data.get("editor") or {},
            creative=data.get("creative_intelligence") or {},
            content_intelligence=data.get("content_intelligence") or {},
        )
        graph["signals"]["vision_mode"] = "predicted"
        graph["signals"]["audio_mode"] = "predicted"
        graph["signals"]["subtitle_mode"] = "predicted"
        return await self._persist(project, graph, organization_id)

    async def analyze_rendered(self, *, project: VideoProject, organization_id=None) -> dict[str, Any]:
        data = dict(project.data or {})
        script = data.get("script") or {}
        storyboard = data.get("scene_director") or data.get("storyboard") or {}
        scenes = list(storyboard.get("scenes") or [])
        editor = data.get("editor") or {}
        production = data.get("production") or {}
        creative = data.get("creative_intelligence") or {}

        graph = self._build_graph(
            project_id=project.id,
            stage="post_render",
            script=script,
            scenes=scenes,
            production=production,
            editor=editor,
            creative=creative,
            content_intelligence=data.get("content_intelligence") or {},
        )

        output_path = Path(str(editor.get("output_path") or "")).resolve()
        if not self._inside_output_dir(output_path):
            raise ValueError("Rendered output is outside the configured output directory")
        if output_path.is_file():
            media = await probe_media(output_path)
            graph["signals"]["media"] = media
            graph["signals"]["subtitle_text_present"] = bool(editor.get("subtitle_path"))
            graph["signals"]["audio_analysis"] = await self._audio_metrics(output_path)
            graph["nodes"].append({
                "id": "media:final",
                "type": "media",
                "status": "present",
                "metadata": media,
            })
            await self._augment_with_multimodal_vision(graph, output_path, scenes, creative, editor)

        result = await self._persist(project, graph, organization_id)
        return result

    async def latest(self, project_id) -> dict[str, Any] | None:
        if self.db is None:
            return None
        row = await self.db.scalar(
            select(ProductionMultimodalGraph)
            .where(ProductionMultimodalGraph.project_id == project_id)
            .order_by(ProductionMultimodalGraph.created_at.desc())
        )
        return self._serialize(row) if row else None

    async def list_graphs(self, project_id, limit: int = 20) -> list[dict[str, Any]]:
        if self.db is None:
            return []
        rows = await self.db.execute(
            select(ProductionMultimodalGraph)
            .where(ProductionMultimodalGraph.project_id == project_id)
            .order_by(ProductionMultimodalGraph.created_at.desc())
            .limit(max(1, min(int(limit), 100)))
        )
        return [self._serialize(row) for row in rows.scalars().all()]

    def _build_graph(
        self,
        *,
        project_id,
        stage: str,
        script: dict[str, Any],
        scenes: list[dict[str, Any]],
        production: dict[str, Any],
        editor: dict[str, Any],
        creative: dict[str, Any],
        content_intelligence: dict[str, Any],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        conflicts: list[dict[str, Any]] = []
        recommendations: list[str] = []
        seen_visuals: Counter[str] = Counter()

        script_text = str(script.get("narration") or script.get("text") or "")
        nodes.append({"id": "script:root", "type": "script", "status": "present" if script else "missing", "metadata": {"title": script.get("title", ""), "chars": len(script_text)}})

        assets = list(production.get("assets") or [])
        asset_by_scene = {int(a.get("scene", 0)): a for a in assets if str(a.get("scene", "")).isdigit()}
        timeline_scenes = list(editor.get("timeline") or [])
        timeline_by_scene = {int(s.get("scene", 0)): s for s in timeline_scenes if str(s.get("scene", "")).isdigit()}

        expected_scene_numbers = list(range(1, len(scenes) + 1))
        actual_scene_numbers = [int(s.get("scene", idx)) for idx, s in enumerate(scenes, start=1)]
        missing_numbers = [n for n in expected_scene_numbers if n not in actual_scene_numbers]
        if missing_numbers:
            conflicts.append({"type": "scene_number_gap", "scenes": missing_numbers, "severity": "high"})

        previous_duration = None
        for index, scene in enumerate(scenes, start=1):
            scene_no = int(scene.get("scene", index))
            narration = str(scene.get("narration") or "").strip()
            visual_prompt = str(scene.get("visual_prompt") or scene.get("visual") or "").strip()
            subtitle_text = str(scene.get("on_screen_text") or "").strip()
            duration = max(0.1, float(scene.get("duration", 0) or 0))
            estimated_audio = self._estimate_speech_seconds(narration)
            visual_key = self._visual_key(visual_prompt)
            seen_visuals[visual_key] += 1

            scene_id = f"scene:{scene_no}"
            nodes.append({"id": scene_id, "type": "scene", "status": "present", "metadata": {"scene": scene_no, "duration_seconds": duration}})

            narration_id = f"narration:{scene_no}"
            nodes.append({"id": narration_id, "type": "narration", "status": "present" if narration else "missing", "metadata": {"chars": len(narration), "estimated_audio_seconds": round(estimated_audio, 2)}})
            edges.append({"from": scene_id, "to": narration_id, "relation": "contains"})

            visual_id = f"visual:{scene_no}"
            visual_status = "present" if visual_prompt else "missing"
            nodes.append({"id": visual_id, "type": "visual", "status": visual_status, "metadata": {"prompt": visual_prompt[:240], "asset_type": scene.get("asset_type", "image")}})
            edges.append({"from": scene_id, "to": visual_id, "relation": "supports"})

            audio_id = f"audio:{scene_no}"
            nodes.append({"id": audio_id, "type": "audio", "status": "predicted" if stage == "pre_render" else "present", "metadata": {"estimated_seconds": round(estimated_audio, 2)}})
            edges.append({"from": scene_id, "to": audio_id, "relation": "voiced_as"})

            subtitle_id = f"subtitle:{scene_no}"
            subtitle_status = "predicted" if stage == "pre_render" else ("present" if subtitle_text or editor.get("subtitle_path") else "missing")
            nodes.append({"id": subtitle_id, "type": "subtitle", "status": subtitle_status, "metadata": {"chars": len(subtitle_text)}})
            edges.append({"from": scene_id, "to": subtitle_id, "relation": "captioned_by"})

            timeline_id = f"timeline:{scene_no}"
            timeline_status = "predicted" if stage == "pre_render" else ("present" if scene_no in timeline_by_scene else "missing")
            nodes.append({"id": timeline_id, "type": "timeline", "status": timeline_status, "metadata": {"duration_seconds": duration}})
            edges.append({"from": scene_id, "to": timeline_id, "relation": "placed_on"})

            asset = asset_by_scene.get(scene_no)
            asset_id = f"asset:{scene_no}"
            asset_status = "planned" if stage == "pre_render" else ("present" if asset and Path(str(asset.get("path", ""))).is_file() else "missing")
            nodes.append({"id": asset_id, "type": "asset", "status": asset_status, "metadata": {"provider": asset.get("source") if asset else None, "path": asset.get("path") if asset else None}})
            edges.append({"from": visual_id, "to": asset_id, "relation": "materialized_as"})

            if not narration:
                conflicts.append({"type": "missing_narration", "scene": scene_no, "severity": "medium"})
            if not visual_prompt:
                conflicts.append({"type": "missing_visual_intent", "scene": scene_no, "severity": "high"})
            if narration and duration + 0.25 < estimated_audio:
                conflicts.append({"type": "audio_overrun_risk", "scene": scene_no, "severity": "high", "details": {"duration": duration, "estimated_audio": round(estimated_audio, 2)}})
            if previous_duration is not None and duration > previous_duration * 3:
                conflicts.append({"type": "duration_jump", "scene": scene_no, "severity": "low"})
            previous_duration = duration

            actual_creative = next((r for r in (creative.get("scene_reports") or []) if int(r.get("scene", 0)) == scene_no), None)
            if actual_creative and float(actual_creative.get("narration_visual_alignment", 1.0) or 0) < 0.55:
                conflicts.append({"type": "narration_visual_mismatch", "scene": scene_no, "severity": "high"})

        for visual_key, count in seen_visuals.items():
            if visual_key and count >= 3:
                conflicts.append({"type": "visual_prompt_repetition", "count": count, "key": visual_key, "severity": "medium"})
                recommendations.append("Regenerate at least one repeated visual concept to improve scene diversity.")

        if conflicts:
            recommendations.extend(self._recommendations_for_conflicts(conflicts))
        score = self._score(conflicts, nodes)
        status = "FAIL" if any(c["severity"] == "high" for c in conflicts) else ("WARN" if conflicts else "PASS")
        risk = "HIGH" if score < 60 else ("MEDIUM" if score < 85 else "LOW")
        graph = {
            "project_id": str(project_id),
            "stage": stage,
            "status": status,
            "score": score,
            "risk_level": risk,
            "nodes": nodes,
            "edges": edges,
            "conflicts": conflicts,
            "recommendations": list(dict.fromkeys(recommendations)),
            "signals": {
                "scene_count": len(scenes),
                "asset_count": len(assets),
                "content_intelligence": bool(content_intelligence),
                "vision_mode": "pending",
                "audio_mode": "pending",
                "subtitle_mode": "pending",
            },
        }
        return graph

    async def _augment_with_multimodal_vision(self, graph: dict[str, Any], output_path: Path, scenes: list[dict[str, Any]], creative: dict[str, Any], editor: dict[str, Any]):
        if not settings.creative_intelligence_enabled or not settings.multimodal_vision_enabled:
            graph["signals"]["vision_mode"] = "disabled"
            return
        with tempfile.TemporaryDirectory(prefix="multimodal-graph-") as tmp:
            frame_paths = await self._extract_frames(output_path, tmp, len(scenes))
            if not frame_paths:
                graph["signals"]["vision_mode"] = "unavailable"
                return
            subtitle_path = Path(str(editor.get("subtitle_path") or "")).resolve() if editor.get("subtitle_path") else None
            if subtitle_path and not self._inside_output_dir(subtitle_path):
                raise ValueError("Subtitle file is outside the configured output directory")
            subtitle_text = await self._read_subtitles(subtitle_path) if subtitle_path else ""
            prompt = json.dumps({
                "task": "Evaluate the whole video contact sheet against its script, storyboard, audio, subtitles and timeline. Return JSON only.",
                "scenes": [
                    {"scene": int(s.get("scene", idx)), "narration": str(s.get("narration", ""))[:600], "visual_goal": str(s.get("visual_goal", ""))[:400], "duration": float(s.get("duration", 0) or 0)}
                    for idx, s in enumerate(scenes, start=1)
                ],
                "timeline": list(editor.get("timeline") or [])[:32],
                "subtitles": subtitle_text[:12000],
                "audio_analysis": graph["signals"].get("audio_analysis") or creative.get("audio_analysis") or {},
                "creative_summary": {
                    "score": creative.get("score"),
                    "issues": creative.get("issues", []),
                    "scene_reports": creative.get("scene_reports", [])[:24],
                },
                "output_schema": {
                    "overall_alignment": 0.0,
                    "storyboard_adherence": 0.0,
                    "visual_variety": 0.0,
                    "scene_findings": [],
                    "recommended_actions": [],
                },
            }, ensure_ascii=False)
            try:
                analyzer = getattr(self.vision, "analyze_multimodal", None)
                if analyzer is None:
                    graph["signals"]["vision_mode"] = "framewise_fallback"
                    return
                result = await analyzer(image_paths=[str(p) for p in frame_paths], prompt=prompt)
                graph["signals"]["vision_mode"] = result.get("_provider", getattr(self.vision, "name", "unknown"))
                graph["signals"]["vision_analysis"] = result
                for finding in result.get("scene_findings", []) or []:
                    try:
                        scene_no = int(finding.get("scene"))
                    except (TypeError, ValueError):
                        continue
                    if float(finding.get("alignment", 1.0) or 0) < 0.55:
                        graph["conflicts"].append({"type": "multimodal_scene_mismatch", "scene": scene_no, "severity": "high", "details": finding})
                graph["score"] = self._score(graph["conflicts"], graph["nodes"])
                graph["status"] = "FAIL" if any(c["severity"] == "high" for c in graph["conflicts"]) else ("WARN" if graph["conflicts"] else "PASS")
                graph["risk_level"] = "HIGH" if graph["score"] < 60 else ("MEDIUM" if graph["score"] < 85 else "LOW")
            except Exception as exc:
                graph["signals"]["vision_mode"] = "error"
                graph["signals"]["vision_error"] = type(exc).__name__

    def _inside_output_dir(self, path: Path) -> bool:
        try:
            path.relative_to(self.output_dir)
            return True
        except ValueError:
            return False

    @staticmethod
    async def _audio_metrics(path: Path) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        text = stderr.decode("utf-8", errors="replace")
        mean = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", text)
        peak = re.search(r"max_volume:\s*(-?[0-9.]+) dB", text)
        return {
            "mean_volume_db": float(mean.group(1)) if mean else None,
            "max_volume_db": float(peak.group(1)) if peak else None,
            "probe_ok": process.returncode == 0,
        }

    @staticmethod
    async def _read_subtitles(path: Path) -> str:
        if not path or not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    async def _extract_frames(self, video_path: Path, tmp_dir: str, scene_count: int) -> list[Path]:
        media = await probe_media(video_path)
        duration = float(media.get("duration_seconds", 0) or 0)
        count = max(4, min(settings.multimodal_max_frames, scene_count or 4))
        if duration <= 0:
            return []
        times = [duration * (i + 0.5) / count for i in range(count)]
        out: list[Path] = []
        for idx, timestamp in enumerate(times, start=1):
            path = Path(tmp_dir) / f"frame_{idx:03d}.jpg"
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-ss", f"{timestamp:.3f}", "-i", str(video_path), "-frames:v", "1", "-q:v", "3", str(path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode == 0 and path.is_file():
                out.append(path)
        return out

    @staticmethod
    def _estimate_speech_seconds(text: str) -> float:
        words = len(re.findall(r"\S+", text))
        if words == 0:
            return 0.0
        return max(0.4, words / 2.45)

    @staticmethod
    def _visual_key(value: str) -> str:
        value = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        return " ".join(value.split())[:140]

    @staticmethod
    def _recommendations_for_conflicts(conflicts: list[dict[str, Any]]) -> list[str]:
        out = []
        kinds = {c.get("type") for c in conflicts}
        if "missing_visual_intent" in kinds:
            out.append("Give every scene an explicit visual intent before asset generation.")
        if "audio_overrun_risk" in kinds:
            out.append("Increase scene duration or shorten narration before rendering.")
        if "scene_number_gap" in kinds:
            out.append("Normalize scene numbering so timeline and asset identity remain deterministic.")
        if "missing_narration" in kinds:
            out.append("Add narration or explicitly mark a scene as non-voiced.")
        if "narration_visual_mismatch" in kinds or "multimodal_scene_mismatch" in kinds:
            out.append("Route the flagged scene to Creative Director for targeted re-edit.")
        return out

    @staticmethod
    def _score(conflicts: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> float:
        score = 100.0
        weights = {"high": 18.0, "medium": 8.0, "low": 3.0}
        for conflict in conflicts:
            score -= weights.get(conflict.get("severity", "low"), 3.0)
        missing = sum(1 for node in nodes if node.get("status") == "missing")
        score -= min(15.0, missing * 2.0)
        return round(max(0.0, min(100.0, score)), 2)

    async def _persist(self, project: VideoProject, result: dict[str, Any], organization_id=None) -> dict[str, Any]:
        if self.db is not None:
            row = ProductionMultimodalGraph(
                organization_id=organization_id,
                channel_id=project.channel_id,
                project_id=project.id,
                stage=result["stage"],
                status=result["status"],
                score=result["score"],
                risk_level=result["risk_level"],
                nodes=result["nodes"],
                edges=result["edges"],
                conflicts=result["conflicts"],
                recommendations=result["recommendations"],
                signals=result["signals"],
            )
            self.db.add(row)
            await self.db.flush()
            result["graph_id"] = str(row.id)
        return result

    @staticmethod
    def _serialize(row: ProductionMultimodalGraph) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "project_id": str(row.project_id),
            "channel_id": str(row.channel_id),
            "stage": row.stage,
            "status": row.status,
            "score": row.score,
            "risk_level": row.risk_level,
            "nodes": row.nodes,
            "edges": row.edges,
            "conflicts": row.conflicts,
            "recommendations": row.recommendations,
            "signals": row.signals,
            "created_at": row.created_at,
        }
