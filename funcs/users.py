"""Funções de usuário: perfil, seguir, bloquear, listas e edição de conta."""

from pathlib import Path

from instagrapi import Client


def info_usuario(cl: Client, username: str):
    """Retorna os dados de um perfil pelo username."""
    return cl.user_info_by_username(username)


def info_usuario_por_id(cl: Client, user_id: str):
    """Retorna os dados de um perfil pelo id numérico."""
    return cl.user_info(user_id)


def id_de_usuario(cl: Client, username: str) -> str:
    """Converte username em user_id."""
    return cl.user_id_from_username(username)


def username_de_id(cl: Client, user_id: str) -> str:
    """Converte user_id em username."""
    return cl.username_from_user_id(user_id)


def seguir(cl: Client, username: str) -> bool:
    """Segue um perfil."""
    return cl.user_follow(cl.user_id_from_username(username))


def deixar_de_seguir(cl: Client, username: str) -> bool:
    """Deixa de seguir um perfil."""
    return cl.user_unfollow(cl.user_id_from_username(username))


def bloquear(cl: Client, username: str) -> bool:
    """Bloqueia um perfil."""
    return cl.user_block(cl.user_id_from_username(username))


def desbloquear(cl: Client, username: str) -> bool:
    """Desbloqueia um perfil."""
    return cl.user_unblock(cl.user_id_from_username(username))


def remover_seguidor(cl: Client, username: str) -> bool:
    """Remove um seguidor do seu perfil."""
    return cl.user_remove_follower(cl.user_id_from_username(username))


def listar_seguidores(cl: Client, username: str, quantidade: int = 0):
    """Lista seguidores (quantidade=0 traz todos)."""
    return cl.user_followers(cl.user_id_from_username(username), amount=quantidade)


def listar_seguindo(cl: Client, username: str, quantidade: int = 0):
    """Lista perfis seguidos (quantidade=0 traz todos)."""
    return cl.user_following(cl.user_id_from_username(username), amount=quantidade)


def pesquisar_usuarios(cl: Client, termo: str):
    """Pesquisa perfis pelo nome ou username."""
    return cl.search_users(termo)


def listar_medias(cl: Client, username: str, quantidade: int = 0):
    """Lista os posts de um perfil."""
    return cl.user_medias(cl.user_id_from_username(username), quantidade)


def listar_reels(cl: Client, username: str, quantidade: int = 0):
    """Lista os Reels de um perfil."""
    return cl.user_clips(cl.user_id_from_username(username), quantidade)


def listar_posts_fixados(cl: Client, username: str):
    """Lista os posts fixados no perfil."""
    return cl.user_pinned_medias(cl.user_id_from_username(username))


def listar_solicitacoes_seguir(cl: Client, quantidade: int = 0):
    """Lista pedidos de seguir pendentes (contas privadas)."""
    return cl.user_follow_requests(quantidade)


def aceitar_solicitacoes(cl: Client, usernames: list[str]):
    """Aceita pedidos de seguir de uma lista de usernames."""
    ids = [cl.user_id_from_username(u) for u in usernames]
    return cl.user_follow_requests_approve(ids)


def recusar_solicitacoes(cl: Client, usernames: list[str]):
    """Recusa pedidos de seguir de uma lista de usernames."""
    ids = [cl.user_id_from_username(u) for u in usernames]
    return cl.user_follow_requests_decline(ids)


def editar_perfil(cl: Client, **campos):
    """Edita campos do perfil (ex.: full_name='Nome', biography='bio')."""
    return cl.account_edit(**campos)


def editar_biografia(cl: Client, biografia: str) -> bool:
    """Atualiza a bio do perfil."""
    return cl.account_set_biography(biografia)


def alterar_foto_perfil(cl: Client, caminho: str | Path):
    """Troca a foto de perfil."""
    return cl.account_change_picture(Path(caminho))


def tornar_privado(cl: Client) -> bool:
    """Torna a conta privada."""
    return cl.account_set_private()


def tornar_publico(cl: Client) -> bool:
    """Torna a conta pública."""
    return cl.account_set_public()
