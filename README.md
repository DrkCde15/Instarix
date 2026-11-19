# Instarix

Projeto inicial para usar o [instagrapi](https://github.com/subzeroid/instagrapi),
uma biblioteca não oficial para a API privada do Instagram, com funções
organizadas por categoria na pasta `funcs/`.

> Automação da API privada é frágil: contas, proxies e desafios podem ser
> restringidos pela Meta. Use apenas para testes, pesquisa ou automação
> controlada de contas próprias, e prefira as APIs oficiais em produção.

## Setup

Já preparado nesta pasta: `.venv` com `instagrapi` e `python-dotenv`
instalados (Python 3.12).

```bash
cp .env.example .env   # preencha IG_USERNAME / IG_PASSWORD
.venv/bin/python main.py
```

Na primeira execução o script faz login e salva a sessão em `session.json`.
As execuções seguintes reutilizam a sessão; o `login()` só autentica de novo
se ela não for mais válida.

## Estrutura

```
main.py              script de exemplo (login + últimos posts)
funcs/               funções organizadas por categoria
├── client.py        conexão e sessão
├── download.py      download de mídias
├── upload.py        publicação
├── delete.py        exclusão
├── media.py         interações com posts
├── users.py         perfis e ações sociais
├── stories.py       stories e destaques
├── direct.py        Instagram Direct
├── insights.py      métricas
├── explore.py       hashtags e locais
├── notes.py         notas
└── music.py         música
examples/            um exemplo de uso por módulo
```

Todas as funções de `funcs/` recebem o client logado como primeiro argumento:

```python
from funcs.client import get_client
from funcs import download

cl = get_client()
download.baixar_midia(cl, "MEDIA_PK", pasta="downloads")
```

`get_client()` lê `IG_USERNAME` / `IG_PASSWORD` do `.env`, reutiliza
`session.json` e aplica um atraso entre requisições (`delay_range = [1, 3]`).

Convenções usadas na documentação abaixo:

- `cl` (omitido nas assinaturas) é sempre o `Client` retornado por `get_client()`.
- `pasta="downloads"` é o destino padrão dos downloads.
- `quantidade=0` significa "todos" nas funções de listagem.
- `media_id` costuma ser `"pk_user_id"`; `media_pk` é só o `pk`.
- `pasta` aceita `str` ou `Path`; caminhos de arquivo também.

## Referência das funções

### funcs.client

| Função | Descrição |
|---|---|
| `get_client(username=None, password=None, session_file=None, proxy=None)` | Cria um `Client` logado, reutilizando a sessão salva quando válida. Sem argumentos, lê as credenciais do `.env`. |

### funcs.download

| Função | Descrição |
|---|---|
| `baixar_foto(media_pk, pasta=PASTA_PADRAO)` | Baixa a imagem de um post. |
| `baixar_video(media_pk, pasta=PASTA_PADRAO)` | Baixa o vídeo de um post comum. |
| `baixar_reel(media_pk, pasta=PASTA_PADRAO)` | Baixa um Reel. |
| `baixar_igtv(media_pk, pasta=PASTA_PADRAO)` | Baixa um vídeo IGTV. |
| `baixar_album(media_pk, pasta=PASTA_PADRAO)` | Baixa todas as mídias de um carrossel (retorna lista de `Path`). |
| `baixar_story(story_pk, pasta=PASTA_PADRAO)` | Baixa uma story pelo pk. |
| `baixar_midia(media_pk, pasta=PASTA_PADRAO)` | Detecta o tipo (foto, vídeo, reel, IGTV ou álbum) e baixa. |
| `baixar_post_por_url(url, pasta=PASTA_PADRAO)` | Baixa um post a partir do link. |
| `baixar_foto_por_url(url, pasta=PASTA_PADRAO)` | Baixa uma imagem direto pela URL do CDN. |
| `baixar_video_por_url(url, pasta=PASTA_PADRAO)` | Baixa um vídeo direto pela URL do CDN. |
| `baixar_todos_posts(username, pasta=PASTA_PADRAO, quantidade=0)` | Baixa todos os posts de um perfil. |
| `baixar_stories_usuario(username, pasta=PASTA_PADRAO)` | Baixa todas as stories ativas de um perfil. |

### funcs.upload

| Função | Descrição |
|---|---|
| `postar_foto(caminho, legenda='', agendar_para=None)` | Publica uma foto no feed. `agendar_para` aceita `datetime` ou timestamp. |
| `postar_video(caminho, legenda='', thumbnail=None, agendar_para=None)` | Publica um vídeo no feed, com thumbnail opcional. |
| `postar_reel(caminho, legenda='', thumbnail=None, trial=False)` | Publica um Reel (`trial=True` para Reel de teste). |
| `postar_igtv(caminho, titulo, legenda='', thumbnail=None)` | Publica um vídeo IGTV. |
| `postar_album(caminhos, legenda='', agendar_para=None)` | Publica um carrossel (2 a 10 fotos/vídeos). |
| `postar_story_foto(caminho, legenda='', mencoes=None, hashtags=None, links=None)` | Publica uma foto nos stories, com menções/hashtags/links opcionais. |
| `postar_story_video(caminho, legenda='', thumbnail=None, mencoes=None, hashtags=None, links=None)` | Publica um vídeo nos stories. |
| `postar_foto_com_musica(caminho, legenda, track)` | Publica uma foto no feed com uma faixa de música. |
| `postar_reel_com_musica(caminho, legenda, track, thumbnail=None)` | Publica um Reel com uma faixa de música. |
| `postar_album_com_musica(caminhos, legenda, track, agendar_para=None)` | Publica um carrossel com uma faixa de música. |
| `postar_story_foto_com_musica(caminho, legenda, track)` | Publica uma foto nos stories com música. |
| `postar_story_video_com_musica(caminho, legenda, track, thumbnail=None)` | Publica um vídeo nos stories com música. |

`track` é um objeto `Track` (converta com `.model_dump()`) ou um `dict`
retornado pelas funções de `funcs.music`.

### funcs.delete

| Função | Descrição |
|---|---|
| `deletar_post(media_id)` | Apaga um post (`media_id` no formato `'pk_user_id'`). |
| `deletar_story(story_pk)` | Apaga uma story publicada. |
| `deletar_destaque(highlight_pk)` | Apaga um destaque (highlight). |
| `deletar_comentario(media_id, comment_pk)` | Apaga um único comentário de um post. |
| `deletar_comentarios(media_id, comment_pks)` | Apaga vários comentários em lote. |
| `deletar_mensagem(thread_id, message_id)` | Apaga uma mensagem do Direct na conversa. |
| `desfazer_mensagem(thread_id, message_id)` | Desfaz (unsend) uma mensagem do Direct para todos. |
| `deletar_nota(note_id)` | Apaga uma nota do perfil. |
| `deletar_quicksnap(media_id)` | Apaga um quicksnap. |

### funcs.media

| Função | Descrição |
|---|---|
| `info_midia(media_pk)` | Retorna os dados completos de um post. |
| `pk_de_url(url)` | Extrai o pk de um post a partir do link. |
| `curtir(media_id)` | Curte um post. |
| `descurtir(media_id)` | Remove a curtida de um post. |
| `salvar(media_id, collection_pk=None)` | Salva um post (opcionalmente em uma coleção). |
| `remover_salvo(media_id, collection_pk=None)` | Remove um post dos salvos. |
| `comentar(media_id, texto, responder_a=None)` | Comenta em um post (`responder_a` = id do comentário a responder). |
| `listar_comentarios(media_id, quantidade=20)` | Lista os comentários de um post. |
| `curtir_comentario(comment_pk)` | Curte um comentário. |
| `descurtir_comentario(comment_pk)` | Remove a curtida de um comentário. |
| `fixar_comentario(media_id, comment_pk)` | Fixa um comentário no post. |
| `desafixar_comentario(media_id, comment_pk)` | Desafixa um comentário do post. |
| `listar_curtidas(media_id)` | Lista quem curtiu um post. |
| `autor_do_post(media_pk)` | Retorna o autor de um post. |
| `editar_legenda(media_id, legenda)` | Edita a legenda de um post. |
| `arquivar(media_id)` | Arquiva um post. |
| `desarquivar(media_id)` | Desarquiva um post. |
| `fixar_post(media_pk)` | Fixa um post no topo do perfil. |
| `desafixar_post(media_pk)` | Desafixa um post do topo do perfil. |

### funcs.users

| Função | Descrição |
|---|---|
| `info_usuario(username)` | Retorna os dados de um perfil pelo username. |
| `info_usuario_por_id(user_id)` | Retorna os dados de um perfil pelo id numérico. |
| `id_de_usuario(username)` | Converte username em `user_id`. |
| `username_de_id(user_id)` | Converte `user_id` em username. |
| `seguir(username)` | Segue um perfil. |
| `deixar_de_seguir(username)` | Deixa de seguir um perfil. |
| `bloquear(username)` | Bloqueia um perfil. |
| `desbloquear(username)` | Desbloqueia um perfil. |
| `remover_seguidor(username)` | Remove um seguidor do seu perfil. |
| `listar_seguidores(username, quantidade=0)` | Lista seguidores. |
| `listar_seguindo(username, quantidade=0)` | Lista perfis seguidos. |
| `pesquisar_usuarios(termo)` | Pesquisa perfis pelo nome ou username. |
| `listar_medias(username, quantidade=0)` | Lista os posts de um perfil. |
| `listar_reels(username, quantidade=0)` | Lista os Reels de um perfil. |
| `listar_posts_fixados(username)` | Lista os posts fixados no perfil. |
| `listar_solicitacoes_seguir(quantidade=0)` | Lista pedidos de seguir pendentes. |
| `aceitar_solicitacoes(usernames)` | Aceita pedidos de seguir de uma lista de usernames. |
| `recusar_solicitacoes(usernames)` | Recusa pedidos de seguir de uma lista de usernames. |
| `editar_perfil(**campos)` | Edita campos do perfil (ex.: `full_name="Nome"`, `biography="bio"`). |
| `editar_biografia(biografia)` | Atualiza a bio do perfil. |
| `alterar_foto_perfil(caminho)` | Troca a foto de perfil. |
| `tornar_privado()` | Torna a conta privada. |
| `tornar_publico()` | Torna a conta pública. |

### funcs.stories

| Função | Descrição |
|---|---|
| `listar_stories(username, quantidade=None)` | Lista as stories ativas de um perfil. |
| `info_story(story_pk)` | Retorna os dados de uma story. |
| `visualizadores(story_pk, quantidade=0)` | Lista quem visualizou uma story sua. |
| `curtir_story(story_id)` | Curte uma story. |
| `descurtir_story(story_id)` | Remove a curtida de uma story. |
| `votar_enquete(story_id, poll_id, voto)` | Vota em uma enquete de story (0 ou 1). |
| `marcar_vistas(story_pks, ignoradas=None)` | Marca stories como vistas. |
| `listar_destaques(username, quantidade=0)` | Lista os destaques (highlights) de um perfil. |
| `criar_destaque(titulo, story_ids, capa='')` | Cria um destaque a partir de stories existentes. |
| `adicionar_ao_destaque(highlight_pk, story_ids)` | Adiciona stories a um destaque. |
| `remover_do_destaque(highlight_pk, story_ids)` | Remove stories de um destaque. |
| `listar_arquivadas(quantidade=0)` | Lista stories arquivadas. |

### funcs.direct

| Função | Descrição |
|---|---|
| `enviar_texto(texto, usernames=None, thread_id=None)` | Envia texto para usuários ou para uma conversa existente. |
| `enviar_foto(caminho, usernames=None, thread_id=None)` | Envia uma foto no Direct. |
| `enviar_video(caminho, usernames=None, thread_id=None)` | Envia um vídeo no Direct. |
| `enviar_audio(caminho, usernames=None, thread_id=None)` | Envia uma mensagem de voz. |
| `enviar_arquivo(caminho, tipo='photo', usernames=None, thread_id=None)` | Envia um arquivo (`tipo='photo'` ou `'video'`). |
| `listar_conversas(quantidade=20)` | Lista as conversas recentes. |
| `listar_mensagens(thread_id, quantidade=20)` | Lista as mensagens de uma conversa. |
| `criar_grupo(usernames, titulo='')` | Cria uma conversa em grupo e retorna o `thread_id`. |
| `adicionar_ao_grupo(thread_id, usernames)` | Adiciona usuários a uma conversa em grupo. |
| `responder(thread_id, texto)` | Responde em uma conversa existente. |
| `reagir(thread_id, message_id, emoji='❤')` | Reage a uma mensagem com um emoji. |

### funcs.insights

| Função | Descrição |
|---|---|
| `insights_conta()` | Retorna as métricas gerais da conta. |
| `insights_post(media_pk)` | Retorna as métricas de um post específico. |
| `insights_feed(tipo_post='ALL', periodo='TWO_YEARS', ordenar_por='REACH_COUNT', quantidade=0)` | Lista métricas de vários posts. `periodo`: `ONE_WEEK`, `ONE_MONTH`, `THREE_MONTHS`, `SIX_MONTHS`, `ONE_YEAR`, `TWO_YEARS`. |

### funcs.explore

| Função | Descrição |
|---|---|
| `info_hashtag(nome)` | Retorna os dados de uma hashtag (sem o `#`). |
| `posts_top_hashtag(nome, quantidade=9)` | Posts em destaque de uma hashtag. |
| `posts_recentes_hashtag(nome, quantidade=27)` | Posts mais recentes de uma hashtag. |
| `seguir_hashtag(nome)` | Segue uma hashtag. |
| `deixar_hashtag(nome)` | Deixa de seguir uma hashtag. |
| `explorar()` | Retorna o feed da aba Explorar. |
| `buscar_locais(latitude, longitude)` | Busca locais próximos a uma coordenada. |
| `info_local(location_pk)` | Retorna os dados de um local. |
| `posts_top_local(location_pk, quantidade=27)` | Posts em destaque de um local. |
| `posts_recentes_local(location_pk, quantidade=63)` | Posts mais recentes de um local. |

### funcs.notes

| Função | Descrição |
|---|---|
| `criar_nota(texto)` | Cria uma nota no perfil (visível por 24h). |
| `listar_notas()` | Lista as notas ativas dos seus contatos. |
| `nota_de_usuario(notas, username)` | Encontra a nota de um usuário na lista de `listar_notas()`. |
| `criar_nota_em_post(media_id, texto='')` | Cria uma nota vinculada a um post. |
| `deletar_nota_em_post(note_id)` | Apaga uma nota vinculada a um post. |

### funcs.music

| Função | Descrição |
|---|---|
| `buscar_musica(termo)` | Busca faixas por nome/artista (lista de `Track`). |
| `buscar_musica_detalhada(termo, produto='music_in_feed')` | Busca detalhada (API v2), com metadados extras. |
| `buscar_por_palavra_chave(termo, produto='music_in_feed', quantidade_palavras=3)` | Busca por palavra-chave; retorna também sugestões de termos. |
| `musicas_trending(produto='feed_post')` | Músicas em alta para o produto informado. |
| `musicas_top_trends(produto='music_in_feed', tamanho_pagina=15)` | Principais tendências musicais. |
| `audios_reels(produto='story_camera_clips_v2')` | Catálogo de áudios disponíveis para Reels. |
| `audios_feed()` | Catálogo de áudios disponíveis para o feed. |
| `info_faixa(track_id)` | Dados de uma faixa pelo id. |
| `info_faixa_por_canonical(music_canonical_id)` | Retorna uma faixa pelo id canônico. |
| `stream_faixa(track_id)` | Informações de stream de uma faixa. |
| `salvar_musica(original_audio_id)` | Salva (bookmark) um áudio original. |
| `listar_musicas_salvas()` | Lista os áudios salvos na conta. |
| `verificar_titulo_original(nome)` | Verifica se o título de áudio original está disponível. |
| `extra_data_reel(track, volume_original=1.0, volume_musica=1.0)` | Monta o `extra_data` de áudio para Reels. |
| `extra_data_story(track, volume_original=0.0, volume_musica=1.0)` | Monta o `extra_data` de áudio para stories. |

`produto` aceita `feed_post`, `music_in_feed` ou `story_camera_clips_v2`.

## Exemplos

A pasta `examples/` tem um arquivo por módulo, com chamadas comentadas e
placeholders. Rode a partir da raiz do projeto:

```bash
python -m examples.download
```

Veja `examples/README.md` para o índice.

## Notas

- Contas com 2FA precisam de `cl.login(user, pass, verification_code="123456")`.
- Mantenha `.env` e `session.json` privados — ambos estão no `.gitignore`.
- Para instalar em outro ambiente: `pip install -r requirements.txt` (Python 3.11+).
