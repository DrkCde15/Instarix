"""Cliente instagrapi compartilhado, com login e sessão persistida."""

import os
from pathlib import Path

from dotenv import load_dotenv
from instagrapi import Client

load_dotenv()

SESSAO_PADRAO = Path(os.getenv("IG_SESSION_FILE", "session.json"))


def get_client(
    username: str | None = None,
    password: str | None = None,
    session_file: str | Path | None = None,
    proxy: str | None = None,
    verification_code: str | None = None,
) -> Client:
    """Cria um Client logado, reutilizando a sessão salva quando válida.

    As credenciais são lidas de IG_USERNAME / IG_PASSWORD (.env) quando não
    forem passadas explicitamente.

    Contas com 2FA precisam do código de verificação em ``verification_code``
    (ou em IG_VERIFICATION_CODE no .env). O código é de uso único e expira
    rápido, então normalmente é passado na hora do login.
    """
    username = username or os.getenv("IG_USERNAME")
    password = password or os.getenv("IG_PASSWORD")
    verification_code = verification_code or os.getenv("IG_VERIFICATION_CODE")
    sessao = Path(session_file or SESSAO_PADRAO)

    if not username or not password:
        raise ValueError(
            "Credenciais ausentes: defina IG_USERNAME e IG_PASSWORD no .env "
            "ou passe username/password."
        )

    cl = Client()
    cl.delay_range = [1, 3]
    if proxy:
        cl.set_proxy(proxy)

    if sessao.exists():
        cl.load_settings(sessao)

    cl.login(username, password, verification_code=verification_code or "")
    cl.dump_settings(sessao)
    return cl
