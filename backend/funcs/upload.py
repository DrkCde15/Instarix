"""Funções de envio: foto, vídeo, reel, IGTV, carrossel e stories."""

from pathlib import Path

from instagrapi import Client


def postar_foto(
    cl: Client,
    caminho: str | Path,
    legenda: str = "",
    agendar_para=None,
):
    """Publica uma foto no feed. `agendar_para` aceita datetime ou timestamp."""
    return cl.photo_upload(Path(caminho), legenda, schedule_at=agendar_para)


def postar_video(
    cl: Client,
    caminho: str | Path,
    legenda: str = "",
    thumbnail: str | Path | None = None,
    agendar_para=None,
):
    """Publica um vídeo no feed, com thumbnail opcional."""
    return cl.video_upload(
        Path(caminho),
        legenda,
        thumbnail=Path(thumbnail) if thumbnail else None,
        schedule_at=agendar_para,
    )


def postar_reel(
    cl: Client,
    caminho: str | Path,
    legenda: str = "",
    thumbnail: str | Path | None = None,
    trial: bool = False,
):
    """Publica um Reel (use trial=True para Reel de teste)."""
    return cl.clip_upload(
        Path(caminho),
        legenda,
        thumbnail=Path(thumbnail) if thumbnail else None,
        trial=trial,
    )


def postar_igtv(
    cl: Client,
    caminho: str | Path,
    titulo: str,
    legenda: str = "",
    thumbnail: str | Path | None = None,
):
    """Publica um vídeo IGTV."""
    return cl.igtv_upload(
        Path(caminho),
        titulo,
        legenda,
        thumbnail=Path(thumbnail) if thumbnail else None,
    )


def postar_album(
    cl: Client,
    caminhos: list[str | Path],
    legenda: str = "",
    agendar_para=None,
):
    """Publica um carrossel (2 a 10 fotos/vídeos)."""
    return cl.album_upload(
        [Path(p) for p in caminhos],
        legenda,
        schedule_at=agendar_para,
    )


def postar_story_foto(
    cl: Client,
    caminho: str | Path,
    legenda: str = "",
    mencoes=None,
    hashtags=None,
    links=None,
):
    """Publica uma foto nos stories, com menções/hashtags/links opcionais."""
    return cl.photo_upload_to_story(
        Path(caminho),
        caption=legenda,
        mentions=mencoes or [],
        hashtags=hashtags or [],
        links=links or [],
    )


def postar_story_video(
    cl: Client,
    caminho: str | Path,
    legenda: str = "",
    thumbnail: str | Path | None = None,
    mencoes=None,
    hashtags=None,
    links=None,
):
    """Publica um vídeo nos stories."""
    return cl.video_upload_to_story(
        Path(caminho),
        caption=legenda,
        thumbnail=Path(thumbnail) if thumbnail else None,
        mentions=mencoes or [],
        hashtags=hashtags or [],
        links=links or [],
    )


def postar_foto_com_musica(
    cl: Client,
    caminho: str | Path,
    legenda: str,
    track: dict,
):
    """Publica uma foto no feed com uma faixa de música (objeto retornado por music_search)."""
    return cl.photo_upload_with_music(Path(caminho), legenda, track)


def postar_reel_com_musica(
    cl: Client,
    caminho: str | Path,
    legenda: str,
    track: dict,
    thumbnail: str | Path | None = None,
):
    """Publica um Reel com uma faixa de música."""
    return cl.clip_upload_with_music(
        Path(caminho),
        legenda,
        track,
        thumbnail=Path(thumbnail) if thumbnail else None,
    )


def postar_album_com_musica(
    cl: Client,
    caminhos: list[str | Path],
    legenda: str,
    track: dict,
    agendar_para=None,
):
    """Publica um carrossel com uma faixa de música."""
    return cl.album_upload_with_music(
        [Path(p) for p in caminhos],
        legenda,
        track,
        schedule_at=agendar_para,
    )


def postar_story_foto_com_musica(
    cl: Client,
    caminho: str | Path,
    legenda: str,
    track: dict,
):
    """Publica uma foto nos stories com uma faixa de música."""
    return cl.photo_upload_to_story_with_music(Path(caminho), legenda, track)


def postar_story_video_com_musica(
    cl: Client,
    caminho: str | Path,
    legenda: str,
    track: dict,
    thumbnail: str | Path | None = None,
):
    """Publica um vídeo nos stories com uma faixa de música."""
    return cl.video_upload_to_story_with_music(
        Path(caminho),
        legenda,
        track,
        thumbnail=Path(thumbnail) if thumbnail else None,
    )
