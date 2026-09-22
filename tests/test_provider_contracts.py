from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.providers.http_llm import OpenAICompatibleLLMProvider
from app.research.http_json import HTTPJSONResearchProvider
from app.research.youtube_data import YouTubeDataResearchProvider


class _FakeAsyncClient:
    def __init__(self, *, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def response(status, payload, method="POST", url="https://provider.test/api"):
    return httpx.Response(status, json=payload, request=httpx.Request(method, url))


def test_openai_compatible_provider_parses_json_and_sends_auth(monkeypatch):
    fake = _FakeAsyncClient(responses=[response(200, {
        "choices": [{"message": {"content": json.dumps({"ok": True, "answer": "hello"})}}]
    })])
    monkeypatch.setattr("app.providers.http_llm.httpx.AsyncClient", lambda **_: fake)

    provider = OpenAICompatibleLLMProvider(
        base_url="https://provider.test",
        api_key="test-key",
        model="test-model",
        timeout_seconds=2,
        max_retries=0,
        use_json_mode=True,
    )
    payload = asyncio.run(provider.generate_json(system="system", user="user"))

    assert payload["ok"] is True
    assert fake.calls[0][2]["headers"]["Authorization"] == "Bearer test-key"
    assert fake.calls[0][2]["json"]["model"] == "test-model"
    assert fake.calls[0][2]["json"]["response_format"] == {"type": "json_object"}


def test_openai_compatible_provider_retries_transient_http_failure(monkeypatch):
    fake = _FakeAsyncClient(responses=[
        response(503, {"error": {"message": "temporary"}}),
        response(200, {"choices": [{"message": {"content": '{"ok": true}'}}]}),
    ])
    monkeypatch.setattr("app.providers.http_llm.httpx.AsyncClient", lambda **_: fake)
    async def no_sleep(_: float) -> None:
        return None
    monkeypatch.setattr("app.providers.http_llm.asyncio.sleep", no_sleep)

    provider = OpenAICompatibleLLMProvider(
        base_url="https://provider.test",
        api_key="test-key",
        model="test-model",
        timeout_seconds=2,
        max_retries=1,
    )
    payload = asyncio.run(provider.generate_json(system="s", user="u"))
    assert payload["ok"] is True
    assert payload["_provider"] == "openai_compatible"
    assert payload["_model"] == "test-model"
    assert len(fake.calls) == 2


def test_http_research_provider_parses_results(monkeypatch):
    fake = _FakeAsyncClient(responses=[response(200, {
        "results": [{"title": "A"}, {"title": "B"}]
    })])
    monkeypatch.setattr("app.research.http_json.httpx.AsyncClient", lambda **_: fake)

    provider = HTTPJSONResearchProvider(endpoint="https://research.test/search", api_key="rk")
    result = asyncio.run(provider.search(query="AI", max_results=2))

    assert [item["title"] for item in result["results"]] == ["A", "B"]
    assert fake.calls[0][2]["headers"]["Authorization"] == "Bearer rk"
    assert fake.calls[0][2]["json"] == {"query": "AI", "max_results": 2}


def test_youtube_research_provider_makes_small_two_request_flow(monkeypatch):
    search_payload = {
        "items": [{
            "id": {"videoId": "vid123"},
            "snippet": {
                "title": "AI Video",
                "description": "Desc",
                "channelId": "chan1",
                "channelTitle": "Channel",
                "publishedAt": "2026-09-01T00:00:00Z",
                "thumbnails": {"high": {"url": "https://img.test/x.jpg"}},
            },
        }]
    }
    video_payload = {
        "items": [{
            "id": "vid123",
            "contentDetails": {"duration": "PT1M"},
            "statistics": {"viewCount": "42", "likeCount": "3", "commentCount": "2"},
        }]
    }
    fake = _FakeAsyncClient(responses=[response(200, search_payload, method="GET"), response(200, video_payload, method="GET")])
    monkeypatch.setattr("app.research.youtube_data.httpx.AsyncClient", lambda **_: fake)

    provider = YouTubeDataResearchProvider(api_key="yt-key", region_code="BE", language="en", order="viewCount")
    result = asyncio.run(provider.search(query="AI agents", max_results=10))

    assert result["provider"] == "youtube_data_api"
    assert result["results"][0]["id"] == "vid123"
    assert result["results"][0]["views"] == 42
    assert len(fake.calls) == 2
    assert fake.calls[0][2]["params"]["maxResults"] == 10
    assert fake.calls[1][2]["params"]["id"] == "vid123"


def test_youtube_research_provider_requires_api_key():
    provider = YouTubeDataResearchProvider(api_key="")
    with pytest.raises(RuntimeError, match="YOUTUBE_RESEARCH_API_KEY"):
        asyncio.run(provider.search(query="AI"))
