"""Funções de exclusão: posts, stories, destaques, comentários, DMs e notas."""

from instagrapi import Client


def deletar_post(cl: Client, media_id: str) -> bool:
    """Apaga um post (media_id no formato 'pk_user_id')."""
    return cl.media_delete(media_id)


def deletar_story(cl: Client, story_pk: str) -> bool:
    """Apaga uma story publicada."""
    return cl.story_delete(story_pk)


def deletar_destaque(cl: Client, highlight_pk: str) -> bool:
    """Apaga um destaque (highlight)."""
    return cl.highlight_delete(highlight_pk)


def deletar_comentario(cl: Client, media_id: str, comment_pk: int) -> bool:
    """Apaga um único comentário de um post."""
    return cl.comment_bulk_delete(media_id, [comment_pk])


def deletar_comentarios(cl: Client, media_id: str, comment_pks: list[int]) -> bool:
    """Apaga vários comentários de um post em lote."""
    return cl.comment_bulk_delete(media_id, comment_pks)


def deletar_mensagem(cl: Client, thread_id: int, message_id: int) -> bool:
    """Apaga uma mensagem do Direct na conversa."""
    return cl.direct_message_delete(thread_id, message_id)


def desfazer_mensagem(cl: Client, thread_id: int, message_id: int) -> bool:
    """Desfaz (unsend) uma mensagem do Direct para todos."""
    return cl.direct_message_unsend(thread_id, message_id)


def deletar_nota(cl: Client, note_id: int) -> bool:
    """Apaga uma nota do perfil."""
    return cl.delete_note(note_id)


def deletar_quicksnap(cl: Client, media_id: str) -> bool:
    """Apaga um quicksnap."""
    return cl.quicksnap_delete(media_id)
