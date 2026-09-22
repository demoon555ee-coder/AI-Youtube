from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet(key: str | None = None) -> Fernet:
    secret = key or settings.app_encryption_key
    if not secret:
        raise RuntimeError("APP_ENCRYPTION_KEY is not configured")
    return Fernet(secret.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not settings.app_encryption_key:
        raise RuntimeError("APP_ENCRYPTION_KEY is not configured")
    try:
        return _fernet(settings.app_encryption_key).decrypt(value.encode()).decode()
    except InvalidToken:
        if settings.app_encryption_key_previous:
            return _fernet(settings.app_encryption_key_previous).decrypt(value.encode()).decode()
        raise


def generate_key() -> str:
    return Fernet.generate_key().decode()
