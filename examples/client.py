"""Exemplo do módulo funcs.client: conexão com sessão persistida."""

from funcs.client import get_client

# Lê IG_USERNAME / IG_PASSWORD do .env e reutiliza session.json se existir.
cl = get_client()

print(f"Conectado como user_id={cl.user_id}")

# Com proxy (opcional):
# cl = get_client(proxy="http://usuario:senha@host:porta")
