from datetime import date, datetime
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.analytics import AnalyticsSnapshot


def _int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def store_analytics_rows(db: AsyncSession, channel_id: str, response: dict) -> int:
    headers = [h.get("name") for h in response.get("columnHeaders", [])]
    count = 0
    for values in response.get("rows", []):
        item = dict(zip(headers, values))
        day_text = item.get("day")
        if not day_text:
            continue
        day = date.fromisoformat(day_text)
        video_id = item.get("video")
        q = await db.execute(
            select(AnalyticsSnapshot).where(
                AnalyticsSnapshot.channel_id == uuid.UUID(channel_id),
                AnalyticsSnapshot.youtube_video_id == video_id,
                AnalyticsSnapshot.day == day,
            )
        )
        row = q.scalar_one_or_none()
        if row is None:
            row = AnalyticsSnapshot(
                channel_id=uuid.UUID(channel_id),
                youtube_video_id=video_id,
                day=day,
            )
            db.add(row)
        row.views = _int(item.get("views"))
        row.watch_time_minutes = _float(item.get("estimatedMinutesWatched"))
        row.average_view_duration = _float(item.get("averageViewDuration"))
        row.average_view_percentage = _float(item.get("averageViewPercentage"))
        row.impressions = _int(item.get("videoThumbnailImpressions") or item.get("video_thumbnail_impressions"))
        row.impression_ctr = _float(item.get("videoThumbnailImpressionsClickRate") or item.get("video_thumbnail_impressions_ctr"))
        row.likes = _int(item.get("likes"))
        row.comments = _int(item.get("comments"))
        row.shares = _int(item.get("shares"))
        row.subscribers_gained = _int(item.get("subscribersGained"))
        row.subscribers_lost = _int(item.get("subscribersLost"))
        row.raw = item
        row.collected_at = datetime.utcnow()
        count += 1
    await db.commit()
    return count
