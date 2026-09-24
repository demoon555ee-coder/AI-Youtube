from app.services import youtube_client


def test_get_mine_channels_paginates_all_pages(monkeypatch):
    calls = []

    class Request:
        def __init__(self, page_token):
            self.page_token = page_token

        def execute(self):
            calls.append(self.page_token)
            if self.page_token is None:
                return {
                    "items": [{"id": "channel-1"}, {"id": "channel-2"}],
                    "nextPageToken": "page-2",
                }
            return {
                "items": [{"id": "channel-3"}],
            }

    class Channels:
        def list(self, **kwargs):
            return Request(kwargs.get("pageToken"))

    class Api:
        def channels(self):
            return Channels()

    monkeypatch.setattr(youtube_client, "youtube_data_api", lambda credentials: Api())

    result = youtube_client.get_mine_channels(object())

    assert [item["id"] for item in result] == ["channel-1", "channel-2", "channel-3"]
    assert calls == [None, "page-2"]


def test_get_mine_channels_raises_when_all_pages_are_empty(monkeypatch):
    class Request:
        def execute(self):
            return {"items": [], "nextPageToken": None}

    class Channels:
        def list(self, **kwargs):
            return Request()

    class Api:
        def channels(self):
            return Channels()

    monkeypatch.setattr(youtube_client, "youtube_data_api", lambda credentials: Api())

    try:
        youtube_client.get_mine_channels(object())
    except RuntimeError as exc:
        assert str(exc) == "No YouTube channel found for authenticated account"
    else:
        raise AssertionError("Expected RuntimeError for an account without channels")
