"""Exemplo do módulo funcs.delete.

ATENÇÃO: estas chamadas apagam conteúdo de verdade. Os IDs são placeholders;
substitua e descomente uma linha por vez.
"""

from funcs import delete
from funcs.client import get_client

cl = get_client()

# delete.deletar_post(cl, "MEDIA_ID")
# delete.deletar_story(cl, "STORY_PK")
# delete.deletar_destaque(cl, "HIGHLIGHT_PK")
# delete.deletar_comentario(cl, "MEDIA_ID", 123456789)
# delete.deletar_comentarios(cl, "MEDIA_ID", [123456789, 987654321])
# delete.deletar_mensagem(cl, thread_id=123456, message_id=987654321)
# delete.desfazer_mensagem(cl, thread_id=123456, message_id=987654321)
# delete.deletar_nota(cl, 123456789)
# delete.deletar_quicksnap(cl, "MEDIA_ID")

print("Exemplos comentados: descomente a operação desejada com um ID real.")
