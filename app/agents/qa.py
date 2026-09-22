from __future__ import annotations
from pathlib import Path
from typing import Any
from app.agents.base import BaseAgent


class QAAgent(BaseAgent):
    name = "qa"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        editor = input_data.get("editor", {})
        production = input_data.get("production", {})
        issues: list[str] = []

        output_path = editor.get("output_path")
        if not output_path or not Path(str(output_path)).exists():
            issues.append("Rendered output is missing")

        assets = production.get("assets", [])
        missing = [a.get("id", "unknown") for a in assets if not Path(str(a.get("path", ""))).exists()]
        if missing:
            issues.append(f"Missing assets: {', '.join(missing)}")

        duration = float(editor.get("duration_seconds") or 0)
        if duration <= 0:
            issues.append("Rendered duration is invalid")

        quality = input_data.get("quality") or {}
        if quality.get("status") == "FAIL":
            issues.extend([f"Quality gate: {issue}" for issue in quality.get("issues", [])])

        return {
            "approved": not issues,
            "issues": issues,
            "checks": {
                "video_exists": bool(output_path and Path(str(output_path)).exists()),
                "assets_exist": not missing,
                "duration_valid": duration > 0,
                "quality_gate": quality.get("status", "UNKNOWN"),
            },
            "quality": quality,
        }
