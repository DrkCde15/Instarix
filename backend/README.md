# Instarix API — Fases 1 a 5

Backend multi-tenant do Instarix: FastAPI + PostgreSQL + SQLAlchemy/Alembic, com
credenciais do Instagram cifradas em repouso. As fases 1–4 entregam auth,
tenants, contas, API keys, login real por conta, 2FA, sessão, health check, fila
de jobs serializada por conta, leituras cacheadas, upload/publicação, webhooks
com HMAC/retry, audit log, quotas por plano, rate limit por API key, métricas,
rotação de chaves e RLS opt-in.

## Stack

- FastAPI + Uvicorn
- PostgreSQL (produção) / SQLite (testes), SQLAlchemy 2.0 síncrono
- Alembic
- Argon2id para senhas de usuários, Fernet para credenciais do Instagram
- JWT de acesso (HS256, 15 min) + refresh token opaco rotativo
- instagrapi para gerar o `device_settings` e executar login/health/logout
- Fila no PostgreSQL (`jobs` + `FOR UPDATE SKIP LOCKED`) processada por um
  worker próprio, sem Redis/arq nesta fase
- Storage local para mídia baixada e uploads (S3/MinIO fica para depois)
- Webhooks de saída com HMAC-SHA256 e retry exponencial
- RLS por tenant no PostgreSQL (opt-in; requer role de worker com BYPASSRLS)

## Rodando localmente

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock

cp .env.example .env
# Preencha JWT_SECRET e SECRETS_KEYS (comandos de geração estão no .env.example)
alembic upgrade head
uvicorn app.main:app --reload
```

Docs interativas em `http://localhost:8000/docs`.

Para desenvolvimento local, `EMBEDDED_WORKER_ENABLED=true` sobe o worker dentro
do próprio Uvicorn, dispensando o segundo terminal. Em produção mantenha
`false` e rode o worker separado.

### Docker

```bash
cd backend
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export SECRETS_KEYS="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
docker compose up --build
```

Os serviços `api` e `worker` compartilham a imagem e o volume `media`. O `api`
aplica `alembic upgrade head` antes de subir o Uvicorn; o `worker` roda
`python -m app.workers.worker` com `JOB_WORKER_THREADS` threads. A senha do
Postgres do compose é apenas para desenvolvimento.

## Testes

```bash
cd backend
pip install -r requirements.lock
pytest
```

`requirements.lock` fixa o ambiente validado pela CI (Python 3.12/Linux),
incluindo as dependências transitivas de teste. `requirements.txt` e
`requirements-dev.txt` mantêm as faixas de versões para atualizações futuras.

Os testes usam SQLite temporário e sobrescrevem `get_db`, `get_device_provider`,
`get_ig_gateway` e o storage de mídia; não precisam de Postgres nem de rede.
Cobrem cripto e rotação de chaves, registro/login/refresh com detecção de reuso,
CRUD de contas, paginação por cursor, RBAC, API keys, isolamento entre tenants,
login (sucesso, 2FA, código errado, expiração, challenge, senha inválida, sessão
inválida e falha transitória), a fase 3 (criação/idempotência/cancelamento de
jobs, serialização por conta, retry/backoff, recuperação pelo sweeper, cache de
mídia/insights e download de assets) e a fase 4 (upload, publicação, proteção
contra post ambíguo, webhooks com HMAC/retry e audit log) e a fase 5 (quotas,
rate limit por API key, métricas, rotação de chaves e RLS opt-in). O teste
`test_migrations.py` compara o schema migrado pelo Alembic com os modelos, e a
suíte também cobre isolamento das métricas por tenant, cookie httpOnly, lock na
rotação do refresh e bloqueio de SSRF.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | sim | `postgresql+psycopg://...`; SQLite aceito para testes |
| `JWT_SECRET` | sim | mínimo 32 caracteres |
| `SECRETS_KEYS` | sim | uma ou mais chaves Fernet separadas por vírgula; a primeira cifra, as demais descriptografam durante rotação |
| `ENVIRONMENT` | não | `dev`/`test`/`prod` |
| `ACCESS_TOKEN_TTL_MINUTES` | não | padrão 15 |
| `REFRESH_TOKEN_TTL_DAYS` | não | padrão 30 |
| `AUTH_COOKIE_SECURE` | não | força `Secure` no cookie de refresh; padrão `true` em `prod` e `false` nos demais |
| `AUTH_COOKIE_SAMESITE` | não | `lax` (padrão), `strict` ou `none`; `none` exige `AUTH_COOKIE_SECURE=true` |
| `AUTH_COOKIE_DOMAIN` | não | domínio do cookie de refresh; vazio usa o host da API |
| `AUTH_REFRESH_COOKIE_NAME` / `AUTH_COOKIE_PATH` | não | nome e path do cookie (padrão `instarix_refresh` / `/v1/auth`) |
| `TRUST_PROXY_HEADERS` | não | usa `X-Forwarded-For` para o IP do cliente; padrão `false`, habilite só atrás de proxy reverso controlado |
| `PROXY_ALLOW_PRIVATE` | não | permite proxies de conta em IPs privados; padrão `false` em `prod` e `true` nos demais ambientes |
| `REGISTRATION_ENABLED` | não | padrão `true`; desative após criar o primeiro tenant |
| `CORS_ORIGINS` | não | lista JSON de origens exatas, ex. `["https://app.exemplo.com"]`; `*` é recusado |
| `AUTH_LOGIN_LIMIT` / `AUTH_LOGIN_WINDOW_SECONDS` | não | tentativas de login por IP (padrão 10 / 5 min); `0` desativa |
| `AUTH_REGISTER_LIMIT` / `AUTH_REGISTER_WINDOW_SECONDS` | não | cadastros por IP (padrão 5 / 1 h) |
| `AUTH_REFRESH_LIMIT` / `AUTH_REFRESH_WINDOW_SECONDS` | não | refresh por IP (padrão 30 / 5 min) |
| `AUTH_MAX_FAILED_LOGINS` / `AUTH_FAILED_LOGIN_WINDOW_SECONDS` | não | falhas por conta antes do lockout (padrão 5 / 15 min) |
| `AUTH_LOCKOUT_SECONDS` | não | duração do lockout por conta (padrão 15 min) |
| `JOB_WORKER_THREADS` | não | threads concorrentes do worker (padrão 2) |
| `EMBEDDED_WORKER_ENABLED` | não | sobe o worker dentro da API; padrão `false`, use apenas em desenvolvimento |
| `JOB_POLL_INTERVAL_SECONDS` | não | intervalo de polling quando a fila está vazia (padrão 2) |
| `JOB_LOCK_TIMEOUT_SECONDS` | não | tempo até o sweeper considerar um job órfão (padrão 600) |
| `JOB_BACKOFF_BASE_SECONDS` | não | base do backoff exponencial com jitter (padrão 5) |
| `MEDIA_STORAGE_DIR` | não | diretório local dos downloads/uploads (padrão `backend/media`) |
| `UPLOAD_MAX_BYTES` | não | tamanho máximo de upload (padrão 25 MiB) |
| `WEBHOOK_TIMEOUT_SECONDS` | não | timeout de cada entrega de webhook (padrão 5 s) |
| `WEBHOOK_MAX_ATTEMPTS` | não | tentativas por entrega (padrão 5) |
| `WEBHOOK_BACKOFF_BASE_SECONDS` | não | base do backoff dos webhooks (padrão 10 s) |
| `API_KEY_RATE_LIMIT` / `API_KEY_RATE_WINDOW_SECONDS` | não | requisições por API key (padrão 600/min); `0` desativa |
| `QUOTA_FREE_ACCOUNTS` / `QUOTA_FREE_JOBS_PER_DAY` | não | quota do plano free (padrão 3 / 100) |
| `QUOTA_PRO_ACCOUNTS` / `QUOTA_PRO_JOBS_PER_DAY` | não | quota do plano pro (padrão 25 / 5000) |
| `RLS_ENABLED` | não | ativa o contexto de RLS na API; padrão `false` |
| `REDIS_URL` | não | reservado; a fila atual usa apenas o PostgreSQL |

## API (v1)

| Método | Rota | Permissão |
|---|---|---|
| POST | `/v1/auth/register` | pública (se `REGISTRATION_ENABLED`) |
| POST | `/v1/auth/token` | pública |
| POST | `/v1/auth/refresh` | refresh token |
| POST | `/v1/auth/logout` | refresh token |
| GET | `/v1/me` | JWT |
| GET/POST | `/v1/accounts` | `accounts:read` / `accounts:write` |
| GET/PATCH/DELETE | `/v1/accounts/{id}` | `accounts:read` / `accounts:write` |
| POST | `/v1/accounts/{id}/login` | `accounts:write` |
| POST | `/v1/accounts/{id}/2fa` | `accounts:2fa` |
| POST | `/v1/accounts/{id}/logout` | `accounts:write` |
| GET | `/v1/accounts/{id}/health` | `accounts:read` |
| GET | `/v1/accounts/{id}/login-attempts` | `accounts:read` |
| GET/POST | `/v1/accounts/{id}/jobs` | `jobs:read` / `jobs:write` |
| GET | `/v1/jobs`, `/v1/jobs/{id}` | `jobs:read` |
| POST | `/v1/jobs/{id}/cancel` | `jobs:write` |
| GET | `/v1/accounts/{id}/media` | `accounts:read` |
| GET | `/v1/media/{asset_id}` | `accounts:read` |
| POST | `/v1/accounts/{id}/insights/sync` | `jobs:write` |
| GET | `/v1/accounts/{id}/insights` | `accounts:read` |
| POST | `/v1/uploads` | `jobs:write` (multipart) |
| GET/POST | `/v1/webhooks` | `webhooks:read` / `webhooks:write` |
| DELETE | `/v1/webhooks/{id}` | `webhooks:write` |
| GET | `/v1/webhooks/{id}/deliveries` | `webhooks:read` |
| GET | `/v1/audit-logs` | `audit:read` |
| GET | `/v1/metrics` | `keys:manage` |
| GET | `/v1/usage` | `accounts:read` |
| GET/POST | `/v1/api-keys` | `keys:manage` |
| DELETE | `/v1/api-keys/{id}` | `keys:manage` |
| GET | `/healthz`, `/readyz` | públicas |

Autenticação: `Authorization: Bearer <access_token>` ou `X-API-Key: ik_live_...`.
`/v1/auth/refresh` e `/v1/auth/logout` aceitam o refresh token no corpo JSON
(para clientes não-browser) ou no cookie httpOnly definido por `/register`,
`/token` e `/refresh`. Erros seguem `{"error": {"code": "...", "message": "..."}}`.

Contas são paginadas por cursor opaco (`?limit=50&cursor=...`); o cursor ordena
por `created_at, id` decrescente. `DELETE /v1/accounts/{id}` é soft delete e
libera o username para recadastro (índice único parcial em `lower(username)`
para contas não deletadas).

## Login e 2FA

O login continua síncrono (não é enfileirado) e roda no threadpool do FastAPI:

1. `POST /v1/accounts/{id}/login` monta um `Client` com o `device_settings`
salvo, proxy e, se houver, a sessão anterior; roda `login(username, password)`
com `delay_range=[1, 3]`.
2. Sucesso → sessão completa (`get_settings()`) é cifrada em `session_enc`,
status `active`, `last_login_at` atualizado e tentativa `succeeded`.
3. 2FA exigido → status `2fa_required`, tentativa `pending_2fa` com validade de
10 minutos; a resposta 200 já traz esse status.
4. `POST /v1/accounts/{id}/2fa` com `{"code": "123456"}` refaz o login com
`verification_code` (o instagrapi resolve o segundo fator na mesma tentativa).
Até 3 códigos por tentativa; código errado devolve `400
invalid_verification_code` com as tentativas restantes. Na terceira falha a
conta vai para `needs_reauth`.
5. Challenge do Instagram → `409 account_challenge_required`; é preciso
resolver no app oficial e então chamar `/login` de novo.
6. Senha recusada → `409 account_needs_reauth` e sessão descartada. Falha de
rede/5xx → `502 instagram_unavailable` sem mudar o status nem consumir a
tentativa de 2FA pendente.

`GET /v1/accounts/{id}/health` valida a sessão com `account_info()`: sessão
recusada vira `needs_reauth` e é apagada; indisponibilidade do Instagram devolve
`502`. `POST /v1/accounts/{id}/logout` tenta o logout remoto (best-effort),
apaga a sessão local e volta para `pending_login`.

`GET /v1/accounts/{id}/login-attempts` lista o histórico (`pending_2fa`,
`succeeded`, `failed`, `expired`, `challenge_required`) sem nunca expor o código.

## Fila de jobs e leituras

A tabela `jobs` no PostgreSQL é a fonte da verdade da fila. O worker faz
`SELECT ... FOR UPDATE SKIP LOCKED` de um job `queued` cujo `run_after` já
passou e cuja conta não tenha outro job `running`. O índice único parcial
`uq_jobs_account_running` garante a serialização por conta mesmo com vários
workers. Jobs de contas diferentes rodam em paralelo.

Tipos aceitos: `media.list`, `media.download`, `insights.account` e
`account.health`. Login/2FA/logout seguem síncronos.

```bash
cd backend
python -m app.workers.worker            # loop com JOB_WORKER_THREADS threads
python -m app.workers.worker --once     # sweeper + processa a fila atual
```

Com `EMBEDDED_WORKER_ENABLED=true`, o `uvicorn` inicia essas mesmas threads no
startup e as encerra no shutdown. Não habilite isso em produção: o worker deve
ser um processo separado para escalar e reiniciar independentemente da API.

- `POST /v1/accounts/{id}/jobs` responde `202` com `Location`. Um
  `idempotency_key` repetido devolve o job existente com `200`.
- `GET /v1/accounts/{id}/jobs` lista os jobs da conta com os mesmos filtros
  (`status`, `type`) e paginação por cursor de `GET /v1/jobs`.
- `POST /v1/jobs/{id}/cancel` só cancela job `queued`; caso contrário `409
  job_not_cancelable`.
- `attempts` sobe no claim. Erros transitórios (`instagram_unavailable`) voltam
  para `queued` com backoff exponencial + jitter, até `max_attempts` (3).
  Sessão recusada/challenge/payload inválido são terminais.
- O sweeper recicla jobs `running` com `locked_at` mais antigo que
  `JOB_LOCK_TIMEOUT_SECONDS` se ainda houver tentativas; senão marca `failed`
  com `job_worker_lost`.
- `GET /v1/accounts/{id}/media` devolve o último `media.list` bem-sucedido ou
  `409 media_not_cached`.
- `media.download` grava o arquivo no storage local e cria `media_assets`;
  `GET /v1/media/{asset_id}` entrega o arquivo com o `content_type` correto.
  Repetir o download da mesma mídia/tipo reaproveita o asset em cache.
- `POST /v1/accounts/{id}/insights/sync` enfileira `insights.account`;
  `GET /v1/accounts/{id}/insights` devolve o último snapshot ou `404
  insights_not_found`.
- A sessão só é descriptografada dentro do handler e nunca entra em `result`,
  logs ou mensagens de erro. Falhas são gravadas como código/mensagem
  sanitizados.

## Uploads, publicação e webhooks

Sem S3/MinIO nesta fase, o upload é multipart direto na API e grava no mesmo
volume local usado pelo worker:

```bash
curl -F file=@foto.jpg -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/uploads
# {"storage_key":"uploads/.../abc.jpg","content_type":"image/jpeg",...}
```

O `storage_key` retornado vai no payload de `publish.photo`, `publish.video`,
`publish.reel`, `publish.album` ou `publish.story`. Limites: 25 MiB,
JPEG/PNG/WebP para foto e MP4/MOV para vídeo. Thumbnail é opcional para vídeo e
reel. O job roda no worker com a sessão da conta. O conteúdo é validado por
magic bytes além de extensão/`Content-Type`; um arquivo com assinatura diferente
do tipo declarado devolve `422 invalid_upload_content`.

Proteção contra post ambíguo: antes de chamar o Instagram o job grava
`result.publish_state = "sending"`. Se a chamada falhar ou o worker morrer, o
job fica `failed` com `ambiguous_publish` e **não** repete sozinho; o cliente
confere a conta antes de reenfileirar. Um replay com a mesma `idempotency_key`
devolve o job existente e não publica de novo.

Webhooks:

- `POST /v1/webhooks` recebe `{url, events}` (`job.succeeded`, `job.failed`) e
  devolve o segredo **uma única vez**. Ele fica cifrado no banco.
- Cada entrega é um POST JSON com `X-Instarix-Event`, `X-Instarix-Delivery`,
  `X-Instarix-Timestamp` e `X-Instarix-Signature: sha256=<hmac>`; o HMAC cobre
  `timestamp.body`, no mesmo formato de Stripe.
- Falhas de rede/HTTP são repetidas com backoff exponencial até
  `WEBHOOK_MAX_ATTEMPTS`; o histórico fica em
  `GET /v1/webhooks/{id}/deliveries`.
- O worker entrega webhooks pendentes no mesmo loop (e no `--once`).

Ações sensíveis geram `audit_logs` sem segredos: criação/atualização/exclusão de
conta, login/2FA/logout, criação/revogação de API key, criação de job e
gestão de webhook. `GET /v1/audit-logs` permite filtrar por `action`,
`account_id` e paginar por cursor.

## Endurecimento

- **Quotas por plano:** `free` (3 contas / 100 jobs por dia) e `pro`
  (25 / 5000); `enterprise` é ilimitado. Criar conta/job acima do limite devolve
  `429 quota_exceeded`. `GET /v1/usage` mostra o consumo. Os limites são
  configuráveis por `QUOTA_*`.
- **Rate limit por API key:** janela deslizante por prefixo (padrão 600/min),
  com `429 api_key_rate_limited` e `Retry-After`. JWT não passa por esse limite.
- **Métricas:** `GET /v1/metrics` (Prometheus, exige `keys:manage`) com jobs por
  tipo/status, profundidade da fila, contas por status, entregas e falhas de
  webhook, todas filtradas pelo tenant do chamador. Alertas recomendados estão
  em [`RUNBOOKS.md`](RUNBOOKS.md).
- **Rotação de chaves:** coloque a chave nova no início de `SECRETS_KEYS` e
  rode `python -m scripts.rotate_secrets`; o script re-cifra contas, sessões e
  segredos de webhook com a chave primária e é idempotente.
- **RLS opt-in:** `python -m scripts.enable_rls --apply` cria policies por
  `tenant_id` nas tabelas de domínio. A API injeta `app.tenant_id` quando
  `RLS_ENABLED=true`; o role do worker precisa de `BYPASSRLS` para reivindicar
  jobs de todos os tenants. Detalhes e rollback em [`RUNBOOKS.md`](RUNBOOKS.md).
- **Carga do dispatcher:** `python -m scripts.load_dispatcher` mede claim
  concorrente e falha se houver job duplicado/não reivindicado.

## Segurança

- Senhas de usuário: Argon2id.
- Senha do Instagram, proxy e `device_settings`: Fernet com ciphertext
  prefixado pelo fingerprint da chave (`<fingerprint>:<token>`). Adicione uma
  chave nova no início de `SECRETS_KEYS` para rotacionar sem perder dados.
- Refresh tokens são opacos e persistidos só como SHA-256. A rotação usa
  `SELECT ... FOR UPDATE` para serializar refreshes concorrentes; reutilizar um
  token já rotacionado revoga a família inteira. O navegador recebe o token em
  cookie `HttpOnly` (e `Secure` fora de desenvolvimento), enquanto o access
  token fica apenas em memória.
- **CSRF:** refresh e logout autenticados por cookie exigem `Origin` igual ao
  host da requisição ou listado em `CORS_ORIGINS` (`403 csrf_origin_rejected`);
  a defesa principal continua sendo `SameSite=lax`. Respostas com tokens saem
  com `Cache-Control: no-store`.
- O CORS usa credenciais (cookie de refresh), então `CORS_ORIGINS` só aceita
  origens exatas — curinga é rejeitado na inicialização, e `SameSite=none`
  exige cookie `Secure`.
- API keys no formato `ik_live_<prefix>_<secret>`, persistidas só como hash e
  limitadas por escopo (`accounts:read`, `accounts:write`, `accounts:2fa`,
  `jobs:read`, `jobs:write`, `keys:manage`).
- Papéis: `owner` tem acesso total; `admin` gerencia contas, jobs, API keys,
  webhooks e auditoria e pode concluir 2FA; `operator` lê contas, conclui 2FA e
  gerencia jobs; `viewer` só lê contas e jobs.
- Toda query de conta/API key filtra por `tenant_id`; IDs de outro tenant
  respondem 404.
- Login tem rate limit por IP e lockout temporário por conta após
  `AUTH_MAX_FAILED_LOGINS` falhas; respostas 429 incluem `Retry-After`. Um login
  bem-sucedido zera as falhas daquela conta, e o bloqueio não revela se o email
  existe (aplica-se igualmente a emails desconhecidos).
- Cadastro e refresh também têm limite por IP. Os limites são aplicados antes
  do Argon2, para não gastar CPU com tentativas bloqueadas.
- A sessão do Instagram (cookies, `authorization_data`, uuids) é cifrada com o
  mesmo esquema da senha; o `device_settings` é gerado uma vez e reutilizado em
  todas as tentativas da conta para não parecer um aparelho novo.
- Códigos 2FA não são persistidos, logados nem devolvidos: só existem no payload
  da requisição e na chamada ao instagrapi. `login_attempts` guarda apenas
  status/contagem/erro.
- Segredos nunca aparecem nas respostas: `AccountOut` expõe apenas `has_proxy`,
  `has_session` e metadados de status/erro.
- **SSRF:** webhooks aceitam só esquema/host válidos e apenas IPs globais
  (privado, loopback, link-local, CGNAT e reservados são recusados). O host é
  resolvido uma única vez e a conexão é feita no IP validado (pinagem), então
  uma segunda resposta DNS não desvia o POST para a rede interna; redirects
  nunca são seguidos. Proxies de conta passam pela mesma checagem (com
  `PROXY_ALLOW_PRIVATE` apenas para desenvolvimento).
- **IP do cliente:** `client_ip()` usa `request.client.host` por padrão e só lê
  `X-Forwarded-For` quando `TRUST_PROXY_HEADERS=true`, evitando que um cliente
  falsifique o IP e burle rate limit/lockout.

## Escopo e limitações desta fase

- 1 tenant por usuário; login apenas por email + senha. Convites e múltiplos
  usuários por tenant ficam para depois.
- Login/health HTTP/logout continuam síncronos: uma chamada pode demorar o
  tempo do handshake com o Instagram. O worker cuida apenas dos quatro tipos de
  job acima.
- Trocar a senha marca a conta como `needs_reauth` e limpa a sessão salva; é
  necessário chamar `/login` de novo. Alterar o proxy não derruba a sessão
  automaticamente.
- 2FA é manual: o usuário informa o código (TOTP/SMS/backup). Seed TOTP
  automático não está implementado.
- O fluxo real não é exercitado no CI (fake do gateway). Falta um teste manual
  com conta real, idealmente antes de expor o endpoint em produção.
- A migration foi exercitada em SQLite (`upgrade`/`downgrade`/`alembic check`);
  não havia Docker/Postgres no ambiente de desenvolvimento, então o caminho
  Postgres (incluindo o `SKIP LOCKED` concorrente) ainda precisa ser validado no
  primeiro `docker compose up`.
- A fila é polling no banco: sem Redis/arq, sem heartbeat durante o job e sem
  prioridade preemptiva. Um job interrompido só é recuperado depois de
  `JOB_LOCK_TIMEOUT_SECONDS`, e jobs longos podem ser reciclados se o timeout
  for menor que a duração real.
- A mídia fica no disco local (`MEDIA_STORAGE_DIR`), sem S3, presign ou
  expiração/retenção. Em várias instâncias, o volume precisa ser compartilhado
  (ou trocado para object storage).
- Não há quota de jobs nem limite de armazenamento por tenant nesta fase.
- Uploads são multipart direto na API, sem URL pré-assinada; o arquivo precisa
  estar no volume compartilhado entre API e worker. A validação combina
  extensão, `Content-Type` e magic bytes dos formatos suportados, mas não faz
  decodificação profunda do arquivo.
- A entrega de webhooks é síncrona dentro do loop do worker, com
  `http.client` sobre o IP pinado. Não há fila dedicada, dead-letter queue nem
  reentrega manual. O IP pinado cobre o DNS rebinding, mas a conexão ainda é
  feita sem `happy eyeballs`/IPv6-first: usa o primeiro endereço global
  resolvido.
- Publicações não têm agendamento (`schedule_at`) nem reconciliação automática
  de post ambíguo; o cliente precisa confirmar na conta.
- O rate limit por API key é em memória por processo; com várias instâncias o
  limite efetivo é multiplicado. Quotas são verificadas por leitura + escrita,
  então duas requisições concorrentes podem passar do limite por uma unidade.
- RLS é opt-in e exige PostgreSQL, policies aplicadas e role de worker com
  `BYPASSRLS`; não é exercitado no SQLite dos testes. As consultas da aplicação
  já filtram `tenant_id` mesmo sem RLS.
- Métricas são calculadas no scrape (sem Prometheus client) e não há alertas
  externos/Sentry integrados; os limiares estão no runbook.

- `alembic check` no SQLite avisa que índices de expressão
  (`lower(email)`, `lower(username)`) não são refletidos; são criados
  explicitamente pela migration e funcionam no Postgres.
- Rate limiting/lockout usam estado em memória **por processo**: com mais de um
  worker ou instância, o limite efetivo é multiplicado pelo número de
  processos. Para produção horizontal, troque o store por Redis mantendo a
  interface de `AuthGuard`. Por padrão o IP é `request.client.host`; atrás de
  proxy reverso, defina `TRUST_PROXY_HEADERS=true` para usar `X-Forwarded-For`
  (o proxy precisa sobrescrever o header, não apenas anexá-lo).

## Próximas fases

6. S3/MinIO com uploads pré-assinados, agendamento de publicação e
   reconciliação de post ambíguo.
7. Alertas externos (Prometheus/Sentry) e rate limit distribuído em Redis.
