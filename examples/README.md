# Exemplos de uso — pasta `funcs`

Cada arquivo mostra as funções principais de um módulo. Rode a partir da raiz
do projeto:

```bash
python -m examples.download
```

Antes de rodar, troque os placeholders (`MEDIA_PK`, `MEDIA_ID`, `STORY_PK`,
`algum_perfil`, nomes de arquivos etc.) pelos valores reais. Ações destrutivas
ou socialmente visíveis (curtir, seguir, apagar, publicar) estão comentadas —
descomente conscientemente.

| Arquivo | Módulo | O que demonstra |
|---|---|---|
| `client.py` | `funcs.client` | conexão e sessão persistida |
| `download.py` | `funcs.download` | baixar posts, perfis e stories |
| `upload.py` | `funcs.upload` | foto, vídeo, reel, carrossel e stories |
| `delete.py` | `funcs.delete` | apagar posts, stories, comentários e DMs |
| `users.py` | `funcs.users` | perfil, seguidores e ações sociais |
| `media.py` | `funcs.media` | curtir, comentar, salvar e editar posts |
| `stories.py` | `funcs.stories` | stories e destaques |
| `direct.py` | `funcs.direct` | conversas, mídia e grupos no Direct |
| `insights.py` | `funcs.insights` | métricas da conta e dos posts |
| `explore.py` | `funcs.explore` | hashtags, locais e aba Explorar |
| `notes.py` | `funcs.notes` | notas do perfil e em posts |
| `music.py` | `funcs.music` | busca, trending e upload com áudio |

Todos os exemplos partem de `cl = get_client()`, que lê `IG_USERNAME` /
`IG_PASSWORD` do `.env` e reutiliza `session.json`.
