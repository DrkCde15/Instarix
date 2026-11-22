"""Re-cifra senhas, proxies, sessões e segredos de webhook com a chave atual.

Uso:
    python -m scripts.rotate_secrets

Coloque a chave nova no início de SECRETS_KEYS e rode este comando. Os
ciphertexts antigos continuam legíveis porque as chaves antigas permanecem
na lista; depois da rotação, remova as chaves antigas quando não houver mais
dados com o fingerprint delas.
"""

import json

from sqlalchemy.orm import Session

from app.core.crypto import get_cipher
from app.db.session import get_engine
from app.services.key_rotation import rotate_secrets


def main() -> int:
    with Session(get_engine()) as db:
        counts = rotate_secrets(db, get_cipher())
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
