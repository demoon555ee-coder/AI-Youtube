import asyncio
from pathlib import Path

from app.agents.storyboard import StoryboardAgent
from app.thumbnail import ThumbnailFactory


def test_storyboard_has_visual_prompts():
    result = asyncio.run(StoryboardAgent().run({"script": {"title": "T", "hook": "H", "sections": [{"type": "hook", "duration": 3, "text": "Hello world"}]}}))
    scene = result["scenes"][0]
    assert scene["visual_prompt"]
    assert scene["shot"] in {"wide", "medium", "close"}


def test_thumbnail_created(tmp_path):
    result = asyncio.run(ThumbnailFactory(str(tmp_path)).create(project_id="p", title="My Video", hook="A hook"))
    assert Path(result["path"]).exists()
    assert result["path"].endswith("thumbnail.png")
