"""Hash de senhas, JWT de acesso e geração de API keys."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings
from app.core.time import utcnow

API_KEY_PREFIX = "ik_live"

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# --- JWT de acesso -----------------------------------------------------------


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, int]:
    now = utcnow()
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": secrets.token_hex(16),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, int(ttl.total_seconds())


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("Tipo de token inválido")
    return payload


# --- API keys ----------------------------------------------------------------


def generate_api_key() -> tuple[str, str, str]:
    """Retorna (chave em claro, prefixo indexável, hash do segredo)."""
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    raw = f"{API_KEY_PREFIX}_{prefix}_{secret}"
    return raw, prefix, hash_api_key_secret(secret)


def parse_api_key(raw: str) -> tuple[str, str] | None:
    parts = raw.split("_", 3)
    if len(parts) != 4 or f"{parts[0]}_{parts[1]}" != API_KEY_PREFIX:
        return None
    prefix, secret = parts[2], parts[3]
    if not prefix or not secret:
        return None
    return prefix, secret


def hash_api_key_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def verify_api_key_secret(secret: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key_secret(secret), expected_hash)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)
