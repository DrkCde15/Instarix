"""Exemplo do módulo funcs.upload: publicar no feed, Reels e stories."""

from funcs import upload
from funcs.client import get_client

cl = get_client()

# Foto no feed.
upload.postar_foto(cl, "foto.jpg", "Minha legenda")

# Vídeo no feed com thumbnail.
upload.postar_video(cl, "video.mp4", "Legenda", thumbnail="capa.jpg")

# Reel.
upload.postar_reel(cl, "reel.mp4", "Legenda do reel")

# Carrossel (2 a 10 arquivos).
upload.postar_album(cl, ["foto1.jpg", "foto2.jpg"], "Legenda do carrossel")

# Stories.
upload.postar_story_foto(cl, "story.jpg", "Legenda do story")
upload.postar_story_video(cl, "story.mp4", "Legenda do story")

# Agendamento (datetime ou timestamp).
# upload.postar_foto(cl, "foto.jpg", "Legenda", agendar_para="2026-12-01 10:00")
