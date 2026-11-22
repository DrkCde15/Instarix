"""Registro, login e rotação de refresh tokens."""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import conflict, forbidden, unauthorized
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.time import as_utc, utcnow
from app.db.models import RefreshToken, Tenant, User


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:70] or "tenant"


def _unique_slug(db: Session, base: str) -> str:
    candidate = base
    suffix = 2
    while db.scalar(select(Tenant.id).where(Tenant.slug == candidate)) is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _issue(db: Session, settings: Settings, user: User, family_id: uuid.UUID | None = None) -> IssuedTokens:
    access_token, expires_in = create_access_token(user.id, settings)
    raw_refresh = generate_refresh_token()
    now = utcnow()
    token = RefreshToken(
        tenant_id=user.tenant_id,
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        created_at=now,
    )
    db.add(token)
    db.commit()
    return IssuedTokens(access_token, raw_refresh, expires_in)


def register(
    db: Session,
    settings: Settings,
    *,
    tenant_name: str,
    email: str,
    password: str,
) -> tuple[User, IssuedTokens]:
    if not settings.registration_enabled:
        raise forbidden("registration_disabled", "Registro desabilitado.")

    email = email.strip().lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        raise conflict("email_taken", "Email já cadastrado.")

    tenant = Tenant(name=tenant_name, slug=_unique_slug(db, slugify(tenant_name)))
    db.add(tenant)
    db.flush()  # gera tenant.id antes de referenciar na FK
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(password),
        role="owner",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("registration_conflict", "Não foi possível criar o tenant.") from exc

    tokens = _issue(db, settings, user)
    return user, tokens


def authenticate(db: Session, settings: Settings, *, email: str, password: str) -> tuple[User, IssuedTokens]:
    email = email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(user.password_hash, password):
        raise unauthorized("invalid_credentials", "Email ou senha inválidos.")
    if not user.is_active:
        raise forbidden("user_inactive", "Usuário desativado.")

    user.last_login_at = utcnow()
    db.commit()
    return user, _issue(db, settings, user)


def rotate_refresh_token(db: Session, settings: Settings, raw_refresh: str) -> IssuedTokens:
    # O lock serializa rotações concorrentes do mesmo token (no Postgres).
    token = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_refresh))
        .with_for_update()
    )
    if token is None:
        raise unauthorized("invalid_refresh_token", "Refresh token inválido.")

    if token.revoked_at is not None:
        # Reuso de token revogado: possível vazamento, derruba a família toda.
        _revoke_family(db, token.family_id)
        raise unauthorized("token_reuse_detected", "Refresh token já utilizado.")

    if as_utc(token.expires_at) <= utcnow():
        raise unauthorized("refresh_expired", "Refresh token expirado.")

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise unauthorized("invalid_refresh_token", "Refresh token inválido.")

    access_token, expires_in = create_access_token(user.id, settings)
    raw_new = generate_refresh_token()
    now = utcnow()
    new_token = RefreshToken(
        tenant_id=token.tenant_id,
        user_id=token.user_id,
        family_id=token.family_id,
        token_hash=hash_refresh_token(raw_new),
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        created_at=now,
    )
    db.add(new_token)
    db.flush()
    token.revoked_at = now
    token.replaced_by_id = new_token.id
    db.commit()
    return IssuedTokens(access_token, raw_new, expires_in)


def revoke_refresh_token(db: Session, raw_refresh: str) -> None:
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_refresh))
    )
    if token is not None and token.revoked_at is None:
        token.revoked_at = utcnow()
        db.commit()


def _revoke_family(db: Session, family_id: uuid.UUID) -> None:
    now = utcnow()
    tokens = db.scalars(
        select(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .with_for_update()
    )
    for token in tokens:
        token.revoked_at = now
    db.commit()
