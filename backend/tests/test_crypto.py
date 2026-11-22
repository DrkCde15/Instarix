import hashlib
import json

import pytest
from cryptography.fernet import Fernet

from app.core.crypto import Cipher, SecretDecryptError


def test_roundtrip_and_json():
    cipher = Cipher([Fernet.generate_key().decode()])
    token = cipher.encrypt("senha-secreta")
    assert "senha-secreta" not in token
    assert cipher.decrypt(token) == "senha-secreta"

    payload = {"device_settings": {"model": "X"}, "uuids": {"uuid": "abc"}}
    assert cipher.decrypt_json(cipher.encrypt_json(payload)) == payload


def test_rotate_adds_new_primary_but_keeps_decrypting_old_data():
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    old_cipher = Cipher([old_key])
    old_token = old_cipher.encrypt("valor-antigo")

    new_cipher = Cipher([new_key, old_key])
    assert new_cipher.decrypt(old_token) == "valor-antigo"

    new_token = new_cipher.encrypt("valor-novo")
    expected_fp = hashlib.sha256(new_key.encode()).hexdigest()[:12]
    assert new_token.startswith(expected_fp + ":")

    # O cipher antigo não conhece a chave nova.
    with pytest.raises(SecretDecryptError):
        old_cipher.decrypt(new_token)


def test_tampered_or_unknown_ciphertext_fails():
    cipher = Cipher([Fernet.generate_key().decode()])
    token = cipher.encrypt("x")
    fingerprint, _, raw = token.partition(":")

    with pytest.raises(SecretDecryptError):
        cipher.decrypt(f"{fingerprint}:{raw[:-1]}A")
    with pytest.raises(SecretDecryptError):
        cipher.decrypt("deadbeefdead:" + raw)
    with pytest.raises(SecretDecryptError):
        cipher.decrypt("sem-separador")


def test_json_payload_is_compact():
    cipher = Cipher([Fernet.generate_key().decode()])
    token = cipher.encrypt_json({"a": 1})
    fingerprint, _, raw = token.partition(":")
    decoded = cipher.decrypt(token)
    assert json.loads(decoded) == {"a": 1}
    assert len(raw) > len(decoded)
