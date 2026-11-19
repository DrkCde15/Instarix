"""Exemplo do módulo funcs.stories: visualizar, curtir e gerenciar destaques."""

from funcs import stories
from funcs.client import get_client

cl = get_client()

# Stories ativas de um perfil.
lista = stories.listar_stories(cl, "algum_perfil")
for story in lista:
    print(story.pk, story.media_type)

# Quem viu uma story sua.
visualizadores = stories.visualizadores(cl, "STORY_PK", quantidade=100)

# Ações (descomente para executar).
# stories.curtir_story(cl, "STORY_ID")
# stories.votar_enquete(cl, "STORY_ID", "POLL_ID", 0)

# Destaques.
destaques = stories.listar_destaques(cl, "algum_perfil")
# stories.criar_destaque(cl, "Nome do destaque", ["STORY_ID_1", "STORY_ID_2"])
# stories.adicionar_ao_destaque(cl, "HIGHLIGHT_PK", ["STORY_ID"])
