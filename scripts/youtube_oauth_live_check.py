from __future__ import annotations

import asyncio
import os

from app.services.youtube_oauth import exchange_code, oauth_client_credentials
from app.services.youtube_client import get_mine_channel


async def main() -> int:
    callback_url = os.getenv("YOUTUBE_OAUTH_CALLBACK_URL", "").strip()
    state = os.getenv("YOUTUBE_OAUTH_STATE", "").strip()
    if not callback_url or not state:
        print("YOUTUBE_OAUTH_CALLBACK_URL and YOUTUBE_OAUTH_STATE are required")
        return 2
    try:
        client_id, _ = oauth_client_credentials()
        credentials = exchange_code(callback_url, state=state)
        channel = get_mine_channel(credentials)
    except Exception as exc:
        print(f"youtube_oauth_check_failed={type(exc).__name__}")
        return 1
    print(f"oauth_client_id_suffix={client_id[-8:]}")
    print(f"youtube_channel_id={channel.get('id', '')}")
    print(f"youtube_channel_title={(channel.get('snippet') or {}).get('title', '')}")
    print("oauth_token_values_not_printed=true")
    print("read_only_after_authorization=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
