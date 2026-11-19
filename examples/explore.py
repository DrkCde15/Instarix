"""Exemplo do módulo funcs.explore: hashtags, locais e aba Explorar."""

from funcs import explore
from funcs.client import get_client

cl = get_client()

# Hashtags.
info = explore.info_hashtag(cl, "automotivo")
top = explore.posts_top_hashtag(cl, "automotivo", quantidade=9)
recentes = explore.posts_recentes_hashtag(cl, "automotivo", quantidade=27)

# Locais (busca por coordenadas).
locais = explore.buscar_locais(cl, latitude=-23.5505, longitude=-46.6333)
if locais:
    pk = locais[0].pk
    detalhes = explore.info_local(cl, pk)
    posts = explore.posts_top_local(cl, pk, quantidade=12)

# Feed da aba Explorar.
pagina = explore.explorar(cl)

# Ações (descomente para executar).
# explore.seguir_hashtag(cl, "automotivo")
# explore.deixar_hashtag(cl, "automotivo")
