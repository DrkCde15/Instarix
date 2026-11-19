"""Funções de download: posts, fotos, vídeos, reels, IGTV, álbuns e stories."""

from pathlib import Path

from instagrapi import Client

PASTA_PADRAO = Path("downloads")


def _pasta(pasta: str | Path | None) -> Path:
    destino = Path(pasta or PASTA_PADRAO)
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def baixar_foto(cl: Client, media_pk: str | int, pasta: str | Path = PASTA_PADRAO) -> Path:
    """Baixa a imagem de um post."""
    return cl.photo_download(media_pk, folder=_pasta(pasta))


def baixar_video(cl: Client, media_pk: str | int, pasta: str | Path = PASTA_PADRAO) -> Path:
    """Baixa o vídeo de um post comum."""
    return cl.video_download(media_pk, folder=_pasta(pasta))


def baixar_reel(cl: Client, media_pk: str | int, pasta: str | Path = PASTA_PADRAO) -> str:
    """Baixa um Reel."""
    return cl.clip_download(media_pk, folder=_pasta(pasta))


def baixar_igtv(cl: Client, media_pk: str | int, pasta: str | Path = PASTA_PADRAO) -> str:
    """Baixa um vídeo IGTV."""
    return cl.igtv_download(media_pk, folder=_pasta(pasta))


def baixar_album(cl: Client, media_pk: str | int, pasta: str | Path = PASTA_PADRAO) -> list[Path]:
    """Baixa todas as mídias de um carrossel."""
    return cl.album_download(media_pk, folder=_pasta(pasta))


def baixar_story(cl: Client, story_pk: str, pasta: str | Path = PASTA_PADRAO) -> Path:
    """Baixa uma story pelo pk."""
    return cl.story_download(story_pk, folder=_pasta(pasta))


def baixar_midia(cl: Client, media_pk: str | int, pasta: str | Path = PASTA_PADRAO):
    """Detecta o tipo do post (foto, vídeo, reel, IGTV ou álbum) e baixa.

    Retorna Path, str ou lista de Paths, conforme o tipo.
    """
    info = cl.media_info(media_pk)
    if info.media_type == 8:  # álbum / carrossel
        return baixar_album(cl, media_pk, pasta)
    if info.product_type == "clips":
        return baixar_reel(cl, media_pk, pasta)
    if info.product_type == "igtv":
        return baixar_igtv(cl, media_pk, pasta)
    if info.media_type == 2:  # vídeo
        return baixar_video(cl, media_pk, pasta)
    return baixar_foto(cl, media_pk, pasta)


def baixar_post_por_url(cl: Client, url: str, pasta: str | Path = PASTA_PADRAO):
    """Baixa um post a partir do link (ex.: instagram.com/p/xxxx)."""
    return baixar_midia(cl, cl.media_pk_from_url(url), pasta)


def baixar_foto_por_url(cl: Client, url: str, pasta: str | Path = PASTA_PADRAO) -> Path:
    """Baixa uma imagem diretamente pela URL do CDN."""
    return cl.photo_download_by_url(url, folder=_pasta(pasta))


def baixar_video_por_url(cl: Client, url: str, pasta: str | Path = PASTA_PADRAO) -> Path:
    """Baixa um vídeo diretamente pela URL do CDN."""
    return cl.video_download_by_url(url, folder=_pasta(pasta))


def baixar_todos_posts(
    cl: Client,
    username: str,
    pasta: str | Path = PASTA_PADRAO,
    quantidade: int = 0,
) -> list:
    """Baixa todos os posts de um perfil (quantidade=0 significa todos)."""
    user_id = cl.user_id_from_username(username)
    return [baixar_midia(cl, media.pk, pasta) for media in cl.user_medias(user_id, quantidade)]


def baixar_stories_usuario(
    cl: Client,
    username: str,
    pasta: str | Path = PASTA_PADRAO,
) -> list[Path]:
    """Baixa todas as stories ativas de um perfil."""
    user_id = cl.user_id_from_username(username)
    return [baixar_story(cl, story.pk, pasta) for story in cl.user_stories(user_id)]
