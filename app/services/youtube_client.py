from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from app.config import settings


def youtube_data_api(credentials: Credentials):
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def youtube_analytics_api(credentials: Credentials):
    return build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)


def get_mine_channels(credentials: Credentials) -> list[dict]:
    result = youtube_data_api(credentials).channels().list(
        part="id,snippet,contentDetails,statistics",
        mine=True,
        maxResults=50,
    ).execute()
    items = result.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel found for authenticated account")
    return items


def get_mine_channel(credentials: Credentials) -> dict:
    return get_mine_channels(credentials)[0]


def upload_video(
    credentials: Credentials,
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str,
    privacy_status: str,
    thumbnail_path: str | None = None,
    publish_at: str | None = None,
) -> dict:
    youtube = youtube_data_api(credentials)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            **({"publishAt": publish_at} if publish_at else {}),
        },
    }
    chunk = settings.upload_chunk_mb * 1024 * 1024
    media = MediaFileUpload(video_path, chunksize=chunk, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]

    if thumbnail_path:
        thumb_media = MediaFileUpload(thumbnail_path, mimetype="image/png")
        youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()

    return response


def query_analytics(credentials: Credentials, channel_id: str, start_date: str, end_date: str, video_id: str | None = None):
    filters = None
    if video_id:
        filters = f"video=={video_id}"

    params = dict(
        ids=f"channel=={channel_id}",
        startDate=start_date,
        endDate=end_date,
        metrics=(
            "views,estimatedMinutesWatched,averageViewDuration,"
            "averageViewPercentage,likes,comments,shares,"
            "subscribersGained,subscribersLost"
        ),
        dimensions="day,video",
        sort="day",
    )
    if filters:
        params["filters"] = filters

    return youtube_analytics_api(credentials).reports().query(**params).execute()
