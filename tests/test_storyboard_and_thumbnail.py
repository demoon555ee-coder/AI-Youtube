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


def test_thumbnail_creates_controlled_variants(tmp_path):
    result = asyncio.run(
        ThumbnailFactory(str(tmp_path)).create(
            project_id="variant-project",
            title="My Video",
            hook="A hook",
        )
    )
    assert result["variant_axis"] == "text_presence"
    assert len(result["variants"]) == 3
    assert {item["variant_id"] for item in result["variants"]} == {"control", "variant_a", "variant_b"}
    for item in result["variants"]:
        assert Path(item["path"]).exists()
    assert Path(result["manifest_path"]).exists()
