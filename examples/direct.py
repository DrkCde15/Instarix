"""Exemplo do módulo funcs.direct: mensagens, mídia e grupos."""

from funcs import direct
from funcs.client import get_client

cl = get_client()

# Conversas e mensagens.
conversas = direct.listar_conversas(cl, quantidade=10)
thread_id = conversas[0].id
mensagens = direct.listar_mensagens(cl, thread_id, quantidade=20)

# Enviar texto para um usuário.
# direct.enviar_texto(cl, "Olá!", usernames=["algum_perfil"])

# Enviar para uma conversa existente.
# direct.enviar_texto(cl, "Olá!", thread_id=thread_id)

# Mídia.
# direct.enviar_foto(cl, "foto.jpg", usernames=["algum_perfil"])
# direct.enviar_video(cl, "video.mp4", usernames=["algum_perfil"])
# direct.enviar_audio(cl, "audio.mp4", thread_id=thread_id)

# Grupos.
# novo_thread = direct.criar_grupo(cl, ["perfil1", "perfil2"], "Meu grupo")

# Reagir a uma mensagem.
# direct.reagir(cl, thread_id, mensagens[0].id, "🔥")
