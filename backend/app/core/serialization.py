"""Normalização de valores antes de gravar em colunas JSON."""

import json
from typing import Any


def json_safe(value: Any) -> Any:
    """Devolve estrutura composta apenas por tipos serializáveis em JSON.

    Respostas de bibliotecas externas (instagrapi) e modelos Pydantic trazem
    tipos como ``HttpUrl``, ``datetime``, ``UUID`` e enums. ``default=str``
    converte todos eles sem perder informação legível.
    """
    return json.loads(json.dumps(value, default=str))
