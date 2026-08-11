"""Fernet symmetric encryption for OAuth tokens."""
from __future__ import annotations

from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode("utf-8"))


def encrypt_str(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_str(token: str) -> str:
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
