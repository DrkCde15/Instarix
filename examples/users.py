"""Exemplo do módulo funcs.users: perfil, seguidores e ações sociais."""

from funcs import users
from funcs.client import get_client

cl = get_client()

# Consultas.
perfil = users.info_usuario(cl, "algum_perfil")
print(perfil.username, perfil.follower_count)

seguidores = users.listar_seguidores(cl, "algum_perfil", quantidade=50)
posts = users.listar_medias(cl, "algum_perfil", quantidade=10)
resultados = users.pesquisar_usuarios(cl, "automotivo")

# Conversões.
user_id = users.id_de_usuario(cl, "algum_perfil")
username = users.username_de_id(cl, user_id)

# Ações (descomente para executar).
# users.seguir(cl, "algum_perfil")
# users.deixar_de_seguir(cl, "algum_perfil")
# users.bloquear(cl, "algum_perfil")
# users.remover_seguidor(cl, "algum_perfil")

# Edição do próprio perfil.
# users.editar_biografia(cl, "Nova bio")
# users.alterar_foto_perfil(cl, "avatar.jpg")
# users.editar_perfil(cl, full_name="Meu Nome")
