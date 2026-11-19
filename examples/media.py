"""Exemplo do módulo funcs.media: curtir, comentar, salvar e editar posts."""

from funcs import media
from funcs.client import get_client

cl = get_client()

# Consultas.
info = media.info_midia(cl, "MEDIA_PK")
print(info.caption_text)

comentarios = media.listar_comentarios(cl, "MEDIA_ID", quantidade=10)
curtidas = media.listar_curtidas(cl, "MEDIA_ID")

# Ações (descomente para executar).
# media.curtir(cl, "MEDIA_ID")
# media.descurtir(cl, "MEDIA_ID")
# media.salvar(cl, "MEDIA_ID")
# media.comentar(cl, "MEDIA_ID", "Ótimo post!")
# media.editar_legenda(cl, "MEDIA_ID", "Nova legenda")
# media.fixar_post(cl, "MEDIA_PK")

# Resultado de comentar é um objeto Comment com o pk do novo comentário.
