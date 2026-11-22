"""Funções de stories e destaques (highlights)."""

from instagrapi import Client


def listar_stories(cl: Client, username: str, quantidade: int | None = None):
    """Lista as stories ativas de um perfil."""
    return cl.user_stories(cl.user_id_from_username(username), amount=quantidade)


def info_story(cl: Client, story_pk: str):
    """Retorna os dados de uma story."""
    return cl.story_info(story_pk)


def visualizadores(cl: Client, story_pk: str | int, quantidade: int = 0):
    """Lista quem visualizou uma story sua."""
    return cl.story_viewers(story_pk, amount=quantidade)


def curtir_story(cl: Client, story_id: str) -> bool:
    """Curti uma story."""
    return cl.story_like(story_id)


def descurtir_story(cl: Client, story_id: str) -> bool:
    """Remove a curtida de uma story."""
    return cl.story_unlike(story_id)


def votar_enquete(cl: Client, story_id: str, poll_id: str, voto: int) -> bool:
    """Vota em uma enquete de story (0 ou 1)."""
    return cl.story_poll_vote(story_id, poll_id, voto)


def marcar_vistas(cl: Client, story_pks: list[int], ignoradas: list[int] | None = None):
    """Marca stories como vistas."""
    return cl.story_seen(story_pks, ignoradas or [])


def listar_destaques(cl: Client, username: str, quantidade: int = 0):
    """Lista os destaques (highlights) de um perfil."""
    return cl.user_highlights(cl.user_id_from_username(username), amount=quantidade)


def criar_destaque(cl: Client, titulo: str, story_ids: list[str], capa: str = ""):
    """Cria um destaque a partir de stories existentes."""
    return cl.highlight_create(titulo, story_ids, cover_story_id=capa)


def adicionar_ao_destaque(cl: Client, highlight_pk: str, story_ids: list[str]):
    """Adiciona stories a um destaque."""
    return cl.highlight_add_stories(highlight_pk, story_ids)


def remover_do_destaque(cl: Client, highlight_pk: str, story_ids: list[str]):
    """Remove stories de um destaque."""
    return cl.highlight_remove_stories(highlight_pk, story_ids)


def listar_arquivadas(cl: Client, quantidade: int = 0):
    """Lista stories arquivadas."""
    return cl.archive_stories(amount=quantidade)
