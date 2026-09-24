from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.youtube import _get_owned_channel
from app.auth.security import Principal


class _ChannelDB:
    def __init__(self, channel):
        self.channel = channel

    async def get(self, model, channel_id):
        return self.channel if self.channel and self.channel.id == channel_id else None


def _principal(*, organization_id=None, scope_key="user-a"):
    return Principal(
        user_id=None,
        organization_id=organization_id,
        role="owner",
        auth_type="test",
        token_id=None,
        scope_key=scope_key,
    )


def test_youtube_channel_ownership_is_tenant_scoped():
    channel_id = uuid4()
    org_a, org_b = uuid4(), uuid4()
    channel = SimpleNamespace(id=channel_id, organization_id=org_b, owner_id="user-b")

    owned = asyncio.run(_get_owned_channel(_ChannelDB(channel), str(channel_id), _principal(organization_id=org_b)))
    assert owned is channel

    with pytest.raises(HTTPException) as error:
        asyncio.run(_get_owned_channel(_ChannelDB(channel), str(channel_id), _principal(organization_id=org_a)))
    assert error.value.status_code == 404


def test_legacy_youtube_channel_ownership_uses_owner_scope():
    channel_id = uuid4()
    channel = SimpleNamespace(id=channel_id, organization_id=None, owner_id="user-a")

    assert asyncio.run(_get_owned_channel(_ChannelDB(channel), str(channel_id), _principal())) is channel
    with pytest.raises(HTTPException) as error:
        asyncio.run(_get_owned_channel(_ChannelDB(channel), str(channel_id), _principal(scope_key="user-b")))
    assert error.value.status_code == 404


def test_youtube_read_and_publish_routes_check_channel_ownership():
    from pathlib import Path

    source = Path("app/api/youtube.py").read_text(encoding="utf-8")
    assert source.count("_get_owned_channel(db, channel_id, principal)") == 4
    assert "return await connection_status(db, str(channel.id))" in source
    assert "return await analytics(db, str(channel.id), payload)" in source


def test_active_workflow_worker_reconciles_execution_controller():
    from pathlib import Path

    source = Path("app/workflows/worker.py").read_text(encoding="utf-8")
    assert "class ObservableWorkflowWorker" in source
    assert "reconcile_workflow(" in source
    assert 'success=True' in source
    assert 'success=False' in source
