"""Funções de música: busca, trending, metadados e dados de áudio para uploads.

Os métodos de busca retornam objetos `Track` (ou dicts da API interna) que
podem ser passados direto para as funções de upload com música em
`funcs.upload`.
"""

from instagrapi import Client

# Produtos aceitos pelos métodos internos de música:
# - "feed_post": post de feed
# - "music_in_feed": música no feed
# - "story_camera_clips_v2": Reels/stories


def buscar_musica(cl: Client, termo: str):
    """Busca faixas de música por nome/artista (retorna lista de Track)."""
    return cl.search_music(termo)


def buscar_musica_detalhada(
    cl: Client,
    termo: str,
    produto: str = "music_in_feed",
):
    """Busca detalhada de músicas (API v2), com metadados extras."""
    return cl.music_search_v2(termo, product=produto)


def buscar_por_palavra_chave(
    cl: Client,
    termo: str,
    produto: str = "music_in_feed",
    quantidade_palavras: int = 3,
):
    """Busca músicas por palavra-chave (retorna sugestões de termos também)."""
    return cl.music_keyword_search(
        termo,
        product=produto,
        num_keywords=quantidade_palavras,
    )


def musicas_trending(cl: Client, produto: str = "feed_post"):
    """Lista as músicas em alta para o produto informado."""
    return cl.music_trending(product=produto)


def musicas_top_trends(
    cl: Client,
    produto: str = "music_in_feed",
    tamanho_pagina: int = 15,
):
    """Lista as principais tendências musicais."""
    return cl.music_top_trends(product=produto, page_size=tamanho_pagina)


def audios_reels(
    cl: Client,
    produto: str = "story_camera_clips_v2",
):
    """Navega pelo catálogo de áudios disponíveis para Reels."""
    return cl.music_clips_audio_browser(product=produto)


def audios_feed(cl: Client):
    """Navega pelo catálogo de áudios disponíveis para o feed."""
    return cl.music_in_feed_audio_browser()


def info_faixa(cl: Client, track_id: str):
    """Retorna os dados de uma faixa pelo id."""
    return cl.track_info_by_id(track_id)


def info_faixa_por_canonical(cl: Client, music_canonical_id: str):
    """Retorna uma faixa pelo id canônico (MusicCanonicalId)."""
    return cl.track_info_by_canonical_id(music_canonical_id)


def stream_faixa(cl: Client, track_id: str):
    """Retorna as informações de stream de uma faixa."""
    return cl.track_stream_info_by_id(track_id)


def salvar_musica(cl: Client, original_audio_id: str) -> bool:
    """Salva (bookmark) um áudio original."""
    return cl.music_bookmark(original_audio_id)


def listar_musicas_salvas(cl: Client):
    """Lista os áudios salvos na conta."""
    return cl.music_bookmarked()


def verificar_titulo_original(cl: Client, nome: str) -> bool:
    """Verifica se o título de áudio original está disponível."""
    return cl.music_verify_original_audio_title(nome)


def extra_data_reel(
    cl: Client,
    track,
    volume_original: float = 1.0,
    volume_musica: float = 1.0,
):
    """Monta o extra_data de áudio para Reels (uso interno do upload)."""
    return cl.clip_music_extra_data(
        track,
        original_volume=volume_original,
        music_volume=volume_musica,
    )


def extra_data_story(
    cl: Client,
    track,
    volume_original: float = 0.0,
    volume_musica: float = 1.0,
):
    """Monta o extra_data de áudio para stories (uso interno do upload)."""
    return cl.story_music_extra_data(
        track,
        original_volume=volume_original,
        music_volume=volume_musica,
    )
