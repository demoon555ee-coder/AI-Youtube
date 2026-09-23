import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from google.oauth2.credentials import Credentials

from app.config import settings
from app.models.channel import Channel
from app.models.youtube_connection import YouTubeConnection
from app.models.publication import Publication
from app.models.domain import VideoProject
from app.oauth.crypto import encrypt, decrypt
from app.services.youtube_oauth import authorization_url, exchange_code, oauth_client_credentials
from app.services.youtube_client import get_mine_channel, upload_video, query_analytics
from app.services.analytics_store import store_analytics_rows




def _persist_refreshed_token(conn: YouTubeConnection, creds: Credentials) -> None:
    if creds.token and creds.token != decrypt(conn.access_token_enc):
        conn.access_token_enc = encrypt(creds.token)
        conn.token_expiry = creds.expiry.replace(tzinfo=None) if creds.expiry else conn.token_expiry

def credentials_from_connection(conn: YouTubeConnection) -> Credentials:
    client_id, client_secret = oauth_client_credentials()
    return Credentials(
        token=decrypt(conn.access_token_enc),
        refresh_token=decrypt(conn.refresh_token_enc),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=(conn.scope or "").split() or None,
    )


async def create_oauth_url(db: AsyncSession, owner_id: str):
    state = uuid.uuid4().hex
    from app.models.oauth_state import OAuthState
    db.add(OAuthState(state=state, owner_id=owner_id))
    await db.commit()
    return authorization_url(state)


async def finish_oauth(db: AsyncSession, callback_url: str, state: str):
    from app.models.oauth_state import OAuthState
    q = await db.execute(select(OAuthState).where(OAuthState.state == state))
    oauth_state = q.scalar_one_or_none()
    if not oauth_state:
        raise RuntimeError("Invalid or expired OAuth state")
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    if now - oauth_state.created_at > timedelta(seconds=settings.oauth_state_ttl_seconds):
        await db.delete(oauth_state)
        await db.commit()
        raise RuntimeError("OAuth state expired")

    creds = exchange_code(callback_url, state)
    if not creds.refresh_token:
        raise RuntimeError("No refresh token returned by Google")

    from app.services.youtube_client import get_mine_channels
    channel_items = get_mine_channels(creds)
    organization_id = None
    try:
        organization_id = uuid.UUID(oauth_state.owner_id)
    except (ValueError, AttributeError):
        pass
    if organization_id is None:
        raise RuntimeError("OAuth state has no valid organization")

    expiry = creds.expiry.replace(tzinfo=None) if creds.expiry else None
    encrypted_access = encrypt(creds.token or "")
    encrypted_refresh = encrypt(creds.refresh_token)
    scope = " ".join(creds.scopes or [])
    connected: list[dict] = []

    for channel_data in channel_items:
        yt_id = channel_data["id"]
        title = channel_data["snippet"]["title"]
        q = await db.execute(select(Channel).where(Channel.youtube_channel_id == yt_id))
        channel = q.scalar_one_or_none()

        if not channel:
            channel = Channel(
                owner_id=oauth_state.owner_id,
                organization_id=organization_id,
                youtube_channel_id=yt_id,
                name=title,
            )
            db.add(channel)
            await db.flush()
        else:
            # A YouTube channel is globally identifiable and must never be reassigned from one organization to another by a new OAuth flow; skip channels already connected to another organization.
            if channel.organization_id and channel.organization_id != organization_id:
                continue
            if not channel.organization_id and channel.owner_id != oauth_state.owner_id:
                continue
            channel.organization_id = organization_id
            channel.owner_id = oauth_state.owner_id
            channel.name = title

        q = await db.execute(select(YouTubeConnection).where(YouTubeConnection.channel_id == channel.id))
        conn = q.scalar_one_or_none()
        if not conn:
            db.add(YouTubeConnection(
                channel_id=channel.id,
                access_token_enc=encrypted_access,
                refresh_token_enc=encrypted_refresh,
                token_expiry=expiry,
                scope=scope,
            ))
        else:
            conn.access_token_enc = encrypted_access
            conn.refresh_token_enc = encrypted_refresh
            conn.token_expiry = expiry
            conn.scope = scope

        connected.append({
            "id": str(channel.id),
            "youtube_channel_id": yt_id,
            "name": title,
            "thumbnail_url": channel_data.get("snippet", {}).get("thumbnails", {}).get("high", {}).get("url")
                or channel_data.get("snippet", {}).get("thumbnails", {}).get("default", {}).get("url"),
            "subscriber_count": int(channel_data.get("statistics", {}).get("subscriberCount", 0) or 0),
        })

    await db.delete(oauth_state)
    await db.commit()
    if not connected:
        raise RuntimeError("No YouTube channels could be linked to this organization")
    return {"channel_id": connected[0]["id"], "channels": connected}


async def connection_status(db: AsyncSession, channel_id: str) -> dict:
    cid = uuid.UUID(channel_id)
    channel = await db.get(Channel, cid)
    if not channel:
        raise RuntimeError("Channel not found")
    q = await db.execute(select(YouTubeConnection).where(YouTubeConnection.channel_id == cid))
    conn = q.scalar_one_or_none()
    return {
        "channel_id": channel_id,
        "connected": conn is not None,
        "youtube_channel_id": channel.youtube_channel_id,
        "token_expiry": conn.token_expiry.isoformat() if conn and conn.token_expiry else None,
    }


async def publish(db: AsyncSession, channel_id: str, project_id: str, payload):
    cid = uuid.UUID(channel_id)
    pid = uuid.UUID(project_id)
    channel = await db.get(Channel, cid)
    project = await db.get(VideoProject, pid)
    if not channel or not project or project.channel_id != cid:
        raise RuntimeError("Channel or project not found")

    existing_publication = await db.scalar(
        select(Publication)
        .where(Publication.project_id == pid, Publication.youtube_video_id.is_not(None))
        .order_by(Publication.created_at.desc())
    )
    if existing_publication and existing_publication.status in {"PUBLISHED", "SCHEDULED"}:
        return {
            "publication_id": str(existing_publication.id),
            "youtube_video_id": existing_publication.youtube_video_id,
            "status": existing_publication.status,
            "idempotent_replay": True,
        }

    q = await db.execute(select(YouTubeConnection).where(YouTubeConnection.channel_id == cid))
    conn = q.scalar_one_or_none()
    if not conn:
        raise RuntimeError("YouTube channel is not connected")

    data = project.data or {}
    video_path = data.get("editor", {}).get("output_path")
    thumbnail_path = data.get("thumbnail", {}).get("path")
    if not video_path:
        raise RuntimeError("Project has no rendered video")

    creds = credentials_from_connection(conn)
    title = payload.title or data.get("script", {}).get("title") or data.get("title") or project.topic
    description = payload.description or data.get("script", {}).get("description", "")
    tags = payload.tags or data.get("research", {}).get("keywords", [])

    publication = Publication(
        project_id=pid,
        status="UPLOADING",
        title=title,
        description=description,
        visibility=payload.privacy_status,
    )
    db.add(publication)
    await db.commit()
    await db.refresh(publication)

    try:
        publish_at = getattr(payload, "publish_at", None)
        if publish_at and payload.privacy_status != "private":
            raise RuntimeError("publish_at requires privacy_status=private")
        result = upload_video(
            creds,
            video_path,
            title,
            description,
            tags,
            payload.category_id,
            payload.privacy_status,
            thumbnail_path,
            publish_at,
        )
        _persist_refreshed_token(conn, creds)
        publication.youtube_video_id = result.get("id")
        scheduled = bool(publish_at)
        publication.status = "SCHEDULED" if scheduled else "PUBLISHED"
        publication.published_at = None if scheduled else datetime.utcnow()
        publication.scheduled_at = datetime.fromisoformat(publish_at.replace("Z", "+00:00")).replace(tzinfo=None) if scheduled else None
        data["publication"] = {"youtube_video_id": publication.youtube_video_id, "status": publication.status, "publish_at": publish_at}
        project.data = data
        project.status = "SCHEDULED" if scheduled else "PUBLISHED"
        await db.commit()
        if publication.youtube_video_id:
            try:
                from app.postpublish.service import PostPublishMonitorService
                from app.portfolio.service import PortfolioService
                portfolio = await PortfolioService(db).ensure(channel.owner_id)
                first_check = publication.scheduled_at if scheduled else None
                await PostPublishMonitorService(db).create(
                    organization_id=channel.organization_id,
                    portfolio_id=portfolio.id,
                    channel_id=channel.id,
                    video_id=publication.youtube_video_id,
                    project_id=project.id,
                    first_check_at=first_check,
                )
            except Exception:
                # Publication success must not be rolled back because monitoring setup failed.
                await db.rollback()
        return {
            "publication_id": str(publication.id),
            "youtube_video_id": publication.youtube_video_id,
            "status": publication.status,
        }
    except Exception as exc:
        publication.status = "FAILED"
        publication.error_message = str(exc)
        await db.commit()
        raise


async def analytics(db: AsyncSession, channel_id: str, payload):
    cid = uuid.UUID(channel_id)
    q = await db.execute(select(YouTubeConnection).where(YouTubeConnection.channel_id == cid))
    conn = q.scalar_one_or_none()
    if not conn:
        raise RuntimeError("YouTube channel is not connected")
    channel = await db.get(Channel, cid)
    if not channel or not channel.youtube_channel_id:
        raise RuntimeError("Channel has no YouTube channel id")
    creds = credentials_from_connection(conn)
    response = query_analytics(creds, channel.youtube_channel_id, payload.start_date, payload.end_date, payload.video_id)
    _persist_refreshed_token(conn, creds)
    stored = await store_analytics_rows(db, channel_id, response)
    return {"stored_rows": stored, "report": response}
