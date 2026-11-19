"""Exemplo do módulo funcs.music: buscar, trending e publicar com áudio."""

from funcs import music, upload
from funcs.client import get_client

cl = get_client()

# Busca simples (retorna objetos Track).
faixas = music.buscar_musica(cl, "nome da musica")
print([f.title for f in faixas[:5]])

# Busca detalhada / por palavra-chave.
detalhada = music.buscar_musica_detalhada(cl, "nome da musica")
palavras = music.buscar_por_palavra_chave(cl, "funk")

# Trending.
tendencia = music.musicas_trending(cl, produto="feed_post")
top = music.musicas_top_trends(cl)

# Publicar com áudio (Track precisa virar dict).
if faixas:
    track = faixas[0].model_dump()
    # upload.postar_reel_com_musica(cl, "reel.mp4", "Legenda", track)
    # upload.postar_foto_com_musica(cl, "foto.jpg", "Legenda", track)
    # upload.postar_story_video_com_musica(cl, "story.mp4", "Legenda", track)

# Salvar áudio original.
# music.salvar_musica(cl, "ORIGINAL_AUDIO_ID")
