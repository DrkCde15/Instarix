"""Funções de interação com posts: curtir, comentar, salvar, fixar e editar."""

from instagrapi import Client


def info_midia(cl: Client, media_pk: str | int):
    """Retorna os dados completos de um post."""
    return cl.media_info(media_pk)


def pk_de_url(cl: Client, url: str) -> str:
    """Extrai o pk de um post a partir do link."""
    return cl.media_pk_from_url(url)


def curtir(cl: Client, media_id: str) -> bool:
    """Curti um post."""
    return cl.media_like(media_id)


def descurtir(cl: Client, media_id: str) -> bool:
    """Remove a curtida de um post."""
    return cl.media_unlike(media_id)


def salvar(cl: Client, media_id: str, collection_pk: int | None = None) -> bool:
    """Salva um post (opcionalmente em uma coleção)."""
    return cl.media_save(media_id, collection_pk=collection_pk)


def remover_salvo(cl: Client, media_id: str, collection_pk: int | None = None) -> bool:
    """Remove um post dos salvos."""
    return cl.media_unsave(media_id, collection_pk=collection_pk)


def comentar(cl: Client, media_id: str, texto: str, responder_a: int | None = None):
    """Comenta em um post (responder_a = id do comentário a responder)."""
    return cl.media_comment(media_id, texto, replied_to_comment_id=responder_a)


def listar_comentarios(cl: Client, media_id: str, quantidade: int = 20):
    """Lista os comentários de um post."""
    return cl.media_comments(media_id, amount=quantidade)


def curtir_comentario(cl: Client, comment_pk: int) -> bool:
    """Curti um comentário."""
    return cl.comment_like(comment_pk)


def descurtir_comentario(cl: Client, comment_pk: int) -> bool:
    """Remove a curtida de um comentário."""
    return cl.comment_unlike(comment_pk)


def fixar_comentario(cl: Client, media_id: str, comment_pk: int):
    """Fixa um comentário no post."""
    return cl.comment_pin(media_id, comment_pk)


def desafixar_comentario(cl: Client, media_id: str, comment_pk: int):
    """Desafixa um comentário do post."""
    return cl.comment_unpin(media_id, comment_pk)


def listar_curtidas(cl: Client, media_id: str):
    """Lista quem curtiu um post."""
    return cl.media_likers(media_id)


def autor_do_post(cl: Client, media_pk: str | int):
    """Retorna o autor de um post."""
    return cl.media_user(media_pk)


def editar_legenda(cl: Client, media_id: str, legenda: str):
    """Edita a legenda de um post."""
    return cl.media_edit(media_id, legenda)


def arquivar(cl: Client, media_id: str) -> bool:
    """Arquiva um post."""
    return cl.media_archive(media_id)


def desarquivar(cl: Client, media_id: str) -> bool:
    """Desarquiva um post."""
    return cl.media_unarchive(media_id)


def fixar_post(cl: Client, media_pk: str):
    """Fixa um post no topo do perfil."""
    return cl.media_pin(media_pk)


def desafixar_post(cl: Client, media_pk: str):
    """Desafixa um post do topo do perfil."""
    return cl.media_unpin(media_pk)
