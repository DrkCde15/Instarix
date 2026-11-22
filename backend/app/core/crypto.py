"""Criptografia simétrica de campos sensíveis, com suporte a rotação de chaves.

Formato do ciphertext: ``<fingerprint>:<token Fernet>``.

O fingerprint identifica a chave usada naquela escrita, então é seguro
adicionar uma chave nova no começo de SECRETS_KEYS: dados antigos continuam
sendo decifrados pela chave antiga, e só precisam ser regravados para migrar.
"""

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class SecretDecryptError(RuntimeError):
    """Ciphertext inválido ou produzido por uma chave que não está configurada."""


def _fingerprint(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:12]


class Cipher:
    def __init__(self, keys: Sequence[str]) -> None:
        if not keys:
            raise ValueError("Nenhuma chave de criptografia configurada")
        self._fernets: dict[str, Fernet] = {}
        self._primary: str | None = None
        for raw in keys:
            key = raw.encode() if isinstance(raw, str) else raw
            fingerprint = _fingerprint(key)
            self._fernets[fingerprint] = Fernet(key)
            if self._primary is None:
                self._primary = fingerprint
        assert self._primary is not None  # garantido pelo check acima

    def encrypt(self, plaintext: str) -> str:
        token = self._fernets[self._primary].encrypt(plaintext.encode())
        return f"{self._primary}:{token.decode()}"

    def decrypt(self, value: str) -> str:
        fingerprint, _, token = value.partition(":")
        fernet = self._fernets.get(fingerprint)
        if not fingerprint or not token or fernet is None:
            raise SecretDecryptError("Ciphertext inválido ou chave ausente")
        try:
            return fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise SecretDecryptError("Não foi possível decifrar o valor") from exc

    def encrypt_json(self, data: dict[str, Any]) -> str:
        return self.encrypt(json.dumps(data, separators=(",", ":"), default=str))

    def decrypt_json(self, value: str) -> dict[str, Any]:
        return json.loads(self.decrypt(value))


_cipher: Cipher | None = None


def get_cipher() -> Cipher:
    global _cipher
    if _cipher is None:
        _cipher = Cipher(get_settings().secret_key_list)
    return _cipher


def reset_cipher() -> None:
    """Limpa o cache (usado em testes)."""
    global _cipher
    _cipher = None
