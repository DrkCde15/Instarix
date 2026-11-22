"""Funções de exploração: hashtags, locais e feed de explorar."""

from instagrapi import Client


def info_hashtag(cl: Client, nome: str):
    """Retorna os dados de uma hashtag (sem o #)."""
    return cl.hashtag_info(nome)


def posts_top_hashtag(cl: Client, nome: str, quantidade: int = 9):
    """Lista os posts em destaque de uma hashtag."""
    return cl.hashtag_medias_top(nome, amount=quantidade)


def posts_recentes_hashtag(cl: Client, nome: str, quantidade: int = 27):
    """Lista os posts mais recentes de uma hashtag."""
    return cl.hashtag_medias_recent(nome, amount=quantidade)


def seguir_hashtag(cl: Client, nome: str) -> bool:
    """Segue uma hashtag."""
    return cl.hashtag_follow(nome)


def deixar_hashtag(cl: Client, nome: str) -> bool:
    """Deixa de seguir uma hashtag."""
    return cl.hashtag_unfollow(nome)


def explorar(cl: Client):
    """Retorna o feed da aba Explorar."""
    return cl.explore_page()


def buscar_locais(cl: Client, latitude: float, longitude: float):
    """Busca locais próximos a uma coordenada."""
    return cl.location_search(latitude, longitude)


def info_local(cl: Client, location_pk: int):
    """Retorna os dados de um local."""
    return cl.location_info(location_pk)


def posts_top_local(cl: Client, location_pk: int, quantidade: int = 27):
    """Lista os posts em destaque de um local."""
    return cl.location_medias_top(location_pk, amount=quantidade)


def posts_recentes_local(cl: Client, location_pk: int, quantidade: int = 63):
    """Lista os posts mais recentes de um local."""
    return cl.location_medias_recent(location_pk, amount=quantidade)
