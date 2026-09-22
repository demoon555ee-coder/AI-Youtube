from __future__ import annotations

import asyncio
import os

import httpx


async def main() -> int:
    api_key = os.getenv("YOUTUBE_RESEARCH_API_KEY", "").strip()
    video_id = os.getenv("YOUTUBE_RESEARCH_VIDEO_ID", "").strip()
    if not api_key or not video_id:
        print("YOUTUBE_RESEARCH_API_KEY and YOUTUBE_RESEARCH_VIDEO_ID are required")
        return 2

    params = {
        "part": "snippet,statistics,contentDetails",
        "id": video_id,
        "key": api_key,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://www.googleapis.com/youtube/v3/videos", params=params)
        response.raise_for_status()
        payload = response.json()

    items = payload.get("items") or []
    if not items:
        print("youtube_video_not_found=true")
        return 1

    item = items[0]
    snippet = item.get("snippet") or {}
    statistics = item.get("statistics") or {}
    print(f"youtube_video_id={item.get('id', '')}")
    print(f"title={snippet.get('title', '')}")
    print(f"views={int(statistics.get('viewCount') or 0)}")
    print("endpoint=videos.list")
    print("read_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
