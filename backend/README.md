# Instarix API — Fases 1, 2 e 3

Backend multi-tenant do Instarix: FastAPI + PostgreSQL + SQLAlchemy/Alembic, com
credenciais do Instagram cifradas em repouso. As fases 1–3 entregam auth,
tenants, contas, API keys, login real por conta, 2FA, sessão, health check e uma
fila de jobs serializada por conta, com operações de leitura/download cacheadas.

## Stack

- FastAPI + Uvicorn
- PostgreSQL (produção) / SQLite (testes), SQLAlchemy 2.0 síncrono
- Alembic
- Argon2id para senhas de usuários, Fernet para credenciais do Instagram
- JWT de acesso (HS256, 15 min) + refresh token opaco rotativo
- instagrapi para gerar o `device_settings` e executar login/health/logout
- Fila no PostgreSQL (`jobs` + `FOR UPDATE SKIP LOCKED`) processada por um
  worker próprio, sem Redis/arq nesta fase
- Storage local para a mídia baixada (S3 fica para a fase 4)

## Rodando localmente

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
# Preencha JWT_SECRET e SECRETS_KEYS (comandos de geração estão no .env.example)
alembic upgrade head
uvicorn app.main:app --reload
```

Docs interativas em `http://localhost:8000/docs`.

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
pip install -r requirements-dev.txt
pytest
```

Os testes usam SQLite temporário e sobrescrevem `get_db`, `get_device_provider`,
`get_ig_gateway` e o storage de mídia; não precisam de Postgres nem de rede.
Cobrem cripto e rotação de chaves, registro/login/refresh com detecção de reuso,
CRUD de contas, paginação por cursor, RBAC, API keys, isolamento entre tenants,
login (sucesso, 2FA, código errado, expiração, challenge, senha inválida, sessão
inválida e falha transitória) e a fase 3: criação/idempotência/cancelamento de
jobs, serialização por conta, retry/backoff, recuperação pelo sweeper, cache de
mídia/insights e download de assets.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | sim | `postgresql+psycopg://...`; SQLite aceito para testes |
| `JWT_SECRET` | sim | mínimo 32 caracteres |
| `SECRETS_KEYS` | sim | uma ou mais chaves Fernet separadas por vírgula; a primeira cifra, as demais descriptografam durante rotação |
| `ENVIRONMENT` | não | `dev`/`test`/`prod` |
| `ACCESS_TOKEN_TTL_MINUTES` | não | padrão 15 |
| `REFRESH_TOKEN_TTL_DAYS` | não | padrão 30 |
| `REGISTRATION_ENABLED` | não | padrão `true`; desative após criar o primeiro tenant |
| `CORS_ORIGINS` | não | lista JSON, ex. `["https://app.exemplo.com"]` |
| `AUTH_LOGIN_LIMIT` / `AUTH_LOGIN_WINDOW_SECONDS` | não | tentativas de login por IP (padrão 10 / 5 min); `0` desativa |
| `AUTH_REGISTER_LIMIT` / `AUTH_REGISTER_WINDOW_SECONDS` | não | cadastros por IP (padrão 5 / 1 h) |
| `AUTH_REFRESH_LIMIT` / `AUTH_REFRESH_WINDOW_SECONDS` | não | refresh por IP (padrão 30 / 5 min) |
| `AUTH_MAX_FAILED_LOGINS` / `AUTH_FAILED_LOGIN_WINDOW_SECONDS` | não | falhas por conta antes do lockout (padrão 5 / 15 min) |
| `AUTH_LOCKOUT_SECONDS` | não | duração do lockout por conta (padrão 15 min) |
| `JOB_WORKER_THREADS` | não | threads concorrentes do worker (padrão 2) |
| `JOB_POLL_INTERVAL_SECONDS` | não | intervalo de polling quando a fila está vazia (padrão 2) |
| `JOB_LOCK_TIMEOUT_SECONDS` | não | tempo até o sweeper considerar um job órfão (padrão 600) |
| `JOB_BACKOFF_BASE_SECONDS` | não | base do backoff exponencial com jitter (padrão 5) |
| `MEDIA_STORAGE_DIR` | não | diretório local dos downloads (padrão `backend/media`) |
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
| GET/POST | `/v1/api-keys` | `keys:manage` |
| DELETE | `/v1/api-keys/{id}` | `keys:manage` |
| GET | `/healthz`, `/readyz` | públicas |

Autenticação: `Authorization: Bearer <access_token>` ou `X-API-Key: ik_live_...`.
Erros seguem `{"error": {"code": "...", "message": "..."}}`.

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

- `POST /v1/accounts/{id}/jobs` responde `202` com `Location`. Um
  `idempotency_key` repetido devolve o job existente com `200`.
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

## Segurança

- Senhas de usuário: Argon2id.
- Senha do Instagram, proxy e `device_settings`: Fernet com ciphertext
  prefixado pelo fingerprint da chave (`<fingerprint>:<token>`). Adicione uma
  chave nova no início de `SECRETS_KEYS` para rotacionar sem perder dados.
- Refresh tokens são opacos e persistidos só como SHA-256; reutilizar um token
  já rotacionado revoga a família inteira.
- API keys no formato `ik_live_<prefix>_<secret>`, persistidas só como hash e
  limitadas por escopo (`accounts:read`, `accounts:write`, `accounts:2fa`,
  `jobs:read`, `jobs:write`, `keys:manage`).
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

- `alembic check` no SQLite avisa que índices de expressão
  (`lower(email)`, `lower(username)`) não são refletidos; são criados
  explicitamente pela migration e funcionam no Postgres.
- Rate limiting/lockout usam estado em memória **por processo**: com mais de um
  worker ou instância, o limite efetivo é multiplicado pelo número de
  processos. Para produção horizontal, troque o store por Redis mantendo a
  interface de `AuthGuard`. O IP usado é `request.client.host`; atrás de proxy
  reverso, habilite os proxy headers do Uvicorn para não limitar todos pelo IP
  do proxy.

## Próximas fases

4. Publicação, uploads, webhooks, S3 e audit log.
5. Quotas, métricas, rotação de chaves e RLS.
