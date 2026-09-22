import asyncio
from pathlib import Path

from app.media import AssetFactory


def test_mock_asset_factory_creates_png(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    # Settings are instantiated at import time, so use a direct factory output dir
    factory = AssetFactory(str(tmp_path), image_provider="mock_png", video_provider="mock_video")
    result = asyncio.run(factory.build_for_storyboard(
        project_id="project-1",
        storyboard={"scenes": [
            {"scene": 1, "duration": 2, "narration": "Hello", "visual_prompt": "A futuristic city"},
            {"scene": 2, "duration": 2, "narration": "World", "visual_prompt": "A robot working"},
        ]},
    ))
    assert result["status"] == "ready"
    assert len(result["assets"]) == 2
    for asset in result["assets"]:
        assert Path(asset["path"]).exists()
        assert asset["path"].endswith(".png")
