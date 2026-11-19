"""Exemplo do módulo funcs.notes: notas do perfil e em posts."""

from funcs import notes
from funcs.client import get_client

cl = get_client()

# Lista as notas ativas dos contatos.
ativas = notes.listar_notas(cl)

# Nota de um usuário específico (usa a lista retornada acima).
nota = notes.nota_de_usuario(cl, ativas, "algum_perfil")
print(nota)

# Ações (descomente para executar).
# notes.criar_nota(cl, "Minha nota de hoje")
# notes.criar_nota_em_post(cl, "MEDIA_ID", "Nota no post")
# notes.deletar_nota_em_post(cl, "NOTE_ID")
