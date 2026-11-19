"""Exemplo do módulo funcs.download: baixar posts, stories e perfis."""

from funcs import download
from funcs.client import get_client

cl = get_client()

# Baixa um post detectando automaticamente foto/vídeo/reel/álbum.
download.baixar_midia(cl, "MEDIA_PK", pasta="downloads")

# Baixa a partir do link do post.
download.baixar_post_por_url(
    cl,
    "https://www.instagram.com/p/XXXXXXXXXXX/",
    pasta="downloads",
)

# Baixa os 20 posts mais recentes de um perfil.
download.baixar_todos_posts(cl, "algum_perfil", pasta="downloads/perfil", quantidade=20)

# Baixa as stories ativas de um perfil.
download.baixar_stories_usuario(cl, "algum_perfil", pasta="downloads/stories")

# Funções específicas: baixar_foto, baixar_video, baixar_reel,
# baixar_igtv, baixar_album, baixar_story.
