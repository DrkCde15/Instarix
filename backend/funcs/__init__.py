"""Funcionalidades do instagrapi organizadas por categoria.

Cada módulo recebe um Client logado (veja funcs.client.get_client) como
primeiro argumento das funções.
"""

from . import client, delete, direct, download, explore, insights, media, music, notes, stories, upload, users

__all__ = [
    "client",
    "delete",
    "direct",
    "download",
    "explore",
    "insights",
    "media",
    "music",
    "notes",
    "stories",
    "upload",
    "users",
]
