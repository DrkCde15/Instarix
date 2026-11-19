"""Funções do Instagram Direct: mensagens, mídia, grupos e reações."""

from pathlib import Path

from instagrapi import Client


def _ids(cl: Client, usernames: list[str]) -> list[int]:
    return [int(cl.user_id_from_username(u)) for u in usernames]


def enviar_texto(
    cl: Client,
    texto: str,
    usernames: list[str] | None = None,
    thread_id: int | None = None,
):
    """Envia uma mensagem de texto para usuários ou para uma conversa existente."""
    if thread_id:
        return cl.direct_send(texto, thread_ids=[thread_id])
    if not usernames:
        raise ValueError("Informe usernames ou thread_id.")
    return cl.direct_send(texto, user_ids=_ids(cl, usernames))


def enviar_foto(
    cl: Client,
    caminho: str | Path,
    usernames: list[str] | None = None,
    thread_id: int | None = None,
):
    """Envia uma foto no Direct."""
    ids = _ids(cl, usernames or [])
    return cl.direct_send_photo(
        Path(caminho),
        user_ids=[] if thread_id else ids,
        thread_ids=[thread_id] if thread_id else [],
    )


def enviar_video(
    cl: Client,
    caminho: str | Path,
    usernames: list[str] | None = None,
    thread_id: int | None = None,
):
    """Envia um vídeo no Direct."""
    ids = _ids(cl, usernames or [])
    return cl.direct_send_video(
        Path(caminho),
        user_ids=[] if thread_id else ids,
        thread_ids=[thread_id] if thread_id else [],
    )


def enviar_audio(
    cl: Client,
    caminho: str | Path,
    usernames: list[str] | None = None,
    thread_id: int | None = None,
):
    """Envia uma mensagem de voz no Direct."""
    ids = _ids(cl, usernames or [])
    return cl.direct_send_voice(
        Path(caminho),
        user_ids=[] if thread_id else ids,
        thread_ids=[thread_id] if thread_id else [],
    )


def enviar_arquivo(
    cl: Client,
    caminho: str | Path,
    tipo: str = "photo",
    usernames: list[str] | None = None,
    thread_id: int | None = None,
):
    """Envia um arquivo no Direct (tipo 'photo' ou 'video')."""
    ids = _ids(cl, usernames or [])
    return cl.direct_send_file(
        Path(caminho),
        user_ids=[] if thread_id else ids,
        thread_ids=[thread_id] if thread_id else [],
        content_type=tipo,
    )


def listar_conversas(cl: Client, quantidade: int = 20):
    """Lista as conversas recentes do Direct."""
    return cl.direct_threads(quantidade)


def listar_mensagens(cl: Client, thread_id: int, quantidade: int = 20):
    """Lista as mensagens de uma conversa."""
    return cl.direct_messages(thread_id, quantidade)


def criar_grupo(cl: Client, usernames: list[str], titulo: str = ""):
    """Cria uma conversa em grupo e retorna o thread_id."""
    return cl.direct_thread_create(_ids(cl, usernames), titulo)


def adicionar_ao_grupo(cl: Client, thread_id: int, usernames: list[str]) -> bool:
    """Adiciona usuários a uma conversa em grupo."""
    return cl.direct_thread_add_users(thread_id, _ids(cl, usernames))


def responder(cl: Client, thread_id: int, texto: str):
    """Responde em uma conversa existente."""
    return cl.direct_answer(thread_id, texto)


def reagir(
    cl: Client,
    thread_id: int,
    message_id: int,
    emoji: str = "❤",
) -> bool:
    """Reage a uma mensagem com um emoji."""
    return cl.direct_send_reaction(thread_id, message_id, emoji)
