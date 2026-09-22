from __future__ import annotations
import asyncio
import os
import shutil
from pathlib import Path
from typing import Any
from app.tts.base import TTSProvider


class EspeakTTSProvider(TTSProvider):
    name = "espeak"

    async def synthesize(self, text: str, output_path: Path, *, language: str = "en", voice: str | None = None, speed: float = 1.0) -> dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        safe_speed = max(80, min(int(175 * speed), 450))
        lang = voice or language or "en"
        executable = shutil.which("espeak") or shutil.which("espeak-ng")
        env = None
        if executable:
            command = [executable, "-v", lang, "-s", str(safe_speed), "-w", str(output_path), text]
        elif os.name == "nt" and shutil.which("powershell.exe"):
            env = os.environ.copy()
            env["ESPEAK_OUTPUT"] = str(output_path)
            env["ESPEAK_TEXT"] = text
            env["ESPEAK_SPEED"] = str(max(-10, min(10, round((safe_speed - 175) / 10))))
            script = "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Rate=[int]$env:ESPEAK_SPEED; $s.SetOutputToWaveFile($env:ESPEAK_OUTPUT); $s.Speak($env:ESPEAK_TEXT); $s.SetOutputToNull(); $s.Dispose()"
            command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]
        else:
            raise RuntimeError("eSpeak executable is not available")
        process = await asyncio.create_subprocess_exec(*command, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"eSpeak failed ({process.returncode}): {detail}")
        return {"provider": self.name, "path": str(output_path)}
