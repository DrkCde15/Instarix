from uuid import UUID

from cryptography.fernet import Fernet

from app.core.crypto import Cipher
from app.db.models import IgAccount, WebhookEndpoint
from app.services.key_rotation import rotate_secrets
from tests.helpers import create_account, register
from tests.test_webhooks import create_webhook


def test_rotate_reencrypts_accounts_and_webhook_secrets(client, session_factory):
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    old_cipher = Cipher([old_key])
    new_cipher = Cipher([new_key, old_key])

    tokens = register(client)
    create_account(client, tokens)
    endpoint = create_webhook(client, tokens).json()

    with session_factory() as db:
        account = db.query(IgAccount).one()
        account.password_enc = old_cipher.encrypt("senha-antiga")
        account.proxy_enc = old_cipher.encrypt("http://user:pass@proxy.local:8080")
        account.device_settings_enc = old_cipher.encrypt_json({"device": "antigo"})
        account.session_enc = old_cipher.encrypt_json(
            {"cookies": {"sessionid": "x"}}
        )
        webhook = db.get(WebhookEndpoint, UUID(endpoint["id"]))
        assert webhook is not None
        webhook.secret_enc = old_cipher.encrypt("segredo-antigo")
        db.commit()

        counts = rotate_secrets(db, new_cipher)
        assert counts == {"accounts": 1, "account_fields": 4, "webhooks": 1}

        account = db.query(IgAccount).one()
        assert not new_cipher.needs_rotation(account.password_enc)
        assert new_cipher.decrypt(account.password_enc) == "senha-antiga"
        assert new_cipher.decrypt(account.proxy_enc).endswith("proxy.local:8080")
        assert new_cipher.decrypt_json(account.device_settings_enc) == {
            "device": "antigo"
        }
        assert new_cipher.decrypt_json(account.session_enc)["cookies"]["sessionid"] == "x"

        webhook = db.query(WebhookEndpoint).one()
        assert not new_cipher.needs_rotation(webhook.secret_enc)
        assert new_cipher.decrypt(webhook.secret_enc) == "segredo-antigo"

        # Rodar de novo é idempotente.
        assert rotate_secrets(db, new_cipher) == {
            "accounts": 0,
            "account_fields": 0,
            "webhooks": 0,
        }
