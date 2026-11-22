"""Re-cifra segredos existentes com a chave primária atual."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import Cipher
from app.db.models import IgAccount, WebhookEndpoint


def rotate_secrets(db: Session, cipher: Cipher) -> dict[str, int]:
    counts = {"accounts": 0, "account_fields": 0, "webhooks": 0}

    for account in db.scalars(select(IgAccount)):
        rotated = 0
        if account.password_enc and cipher.needs_rotation(account.password_enc):
            account.password_enc = cipher.encrypt(cipher.decrypt(account.password_enc))
            rotated += 1
        if account.proxy_enc and cipher.needs_rotation(account.proxy_enc):
            account.proxy_enc = cipher.encrypt(cipher.decrypt(account.proxy_enc))
            rotated += 1
        if account.device_settings_enc and cipher.needs_rotation(
            account.device_settings_enc
        ):
            account.device_settings_enc = cipher.encrypt_json(
                cipher.decrypt_json(account.device_settings_enc)
            )
            rotated += 1
        if account.session_enc and cipher.needs_rotation(account.session_enc):
            account.session_enc = cipher.encrypt_json(
                cipher.decrypt_json(account.session_enc)
            )
            rotated += 1
        if rotated:
            counts["accounts"] += 1
            counts["account_fields"] += rotated

    for endpoint in db.scalars(select(WebhookEndpoint)):
        if cipher.needs_rotation(endpoint.secret_enc):
            endpoint.secret_enc = cipher.encrypt(cipher.decrypt(endpoint.secret_enc))
            counts["webhooks"] += 1

    db.commit()
    return counts
