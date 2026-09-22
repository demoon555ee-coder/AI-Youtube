#!/usr/bin/env python3
"""Re-encrypt stored YouTube credentials and session CSRF secrets with APP_ENCRYPTION_KEY.

Rotation procedure:
1. Set APP_ENCRYPTION_KEY to the new key and APP_ENCRYPTION_KEY_PREVIOUS to the old key.
2. Run this command once against the production database.
3. Verify the row count and successful decryption in staging/production logs.
4. Remove APP_ENCRYPTION_KEY_PREVIOUS only after the rotation has completed.

No plaintext credential values are printed.
"""
from __future__ import annotations

import asyncio
from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models.youtube_connection import YouTubeConnection
from app.models.auth import AuthSession
from app.oauth.crypto import decrypt, encrypt, generate_key


async def rotate() -> int:
    async with SessionLocal() as db:
        rows = (await db.execute(select(YouTubeConnection))).scalars().all()
        sessions = (await db.execute(select(AuthSession))).scalars().all()
        changed = 0
        for row in rows:
            access = decrypt(row.access_token_enc)
            refresh = decrypt(row.refresh_token_enc)
            row.access_token_enc = encrypt(access)
            row.refresh_token_enc = encrypt(refresh)
            changed += 1
        for session in sessions:
            if session.csrf_token_enc:
                csrf = decrypt(session.csrf_token_enc)
                session.csrf_token_enc = encrypt(csrf)
        await db.commit()
        return changed


async def main() -> None:
    print(f"Suggested new Fernet key: {generate_key()}")
    print("Stored credentials will only be re-encrypted when the command is run with the new key configured.")
    count = await rotate()
    print(f"Rotated encrypted YouTube credential rows: {count}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
