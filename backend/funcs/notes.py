"""Funções de notas (Notes) do Instagram."""

from instagrapi import Client


def criar_nota(cl: Client, texto: str):
    """Cria uma nota no perfil (visível por 24h)."""
    return cl.create_note(texto)


def listar_notas(cl: Client):
    """Lista as notas ativas dos seus contatos."""
    return cl.get_notes()


def nota_de_usuario(cl: Client, notas: list, username: str):
    """Encontra a nota de um usuário na lista retornada por listar_notas()."""
    return cl.get_note_by_user(notas, username)


def criar_nota_em_post(cl: Client, media_id: str, texto: str = ""):
    """Cria uma nota vinculada a um post."""
    return cl.media_note_create(media_id, texto)


def deletar_nota_em_post(cl: Client, note_id: str) -> bool:
    """Apaga uma nota vinculada a um post."""
    return cl.media_note_delete(note_id)
