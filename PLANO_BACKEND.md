# Plano do backend — Instarix multi-conta (multi-tenant)

Status: rascunho para revisão. Nada aqui foi implementado ainda.
Base: o projeto atual (`funcs/`) é uma camada fina sobre o `instagrapi` 3.2.
O backend será uma API multi-tenant em volta dele, com filas e persistência
de sessão por conta.

## 1. Escopo

Serviço HTTP onde vários tenants cadastram **contas do Instagram** e executam
operações nelas (login com 2FA, leitura de perfis/mídias, download, publicação,
insights, Direct), com isolamento de dados, credenciais criptografadas,
serialização por conta e histórico de jobs.

Fora de escopo nesta primeira versão:

- API pública/anônima; todo acesso é autenticado e escopado por tenant.
- Múltiplas sessões simultâneas para a mesma conta do Instagram.
- Loops automáticos de follow/unfollow/curtidas em massa.
- Frontend.
- Uso da API oficial da Meta (pode entrar como fallback futuro).

Premissa de risco: a API privada do Instagram é frágil e não oficial. O backend
precisa tratar `challenge_required` como estado terminal que exige ação humana,
nunca como erro transitório para retry.

## 2. Stack e justificativa

| Camada | Escolha | Por quê |
|---|---|---|
| API | FastAPI | async, OpenAPI automático, mesmo ecossistema Python do `funcs/` |
| Banco | PostgreSQL 16 | transações, `SKIP LOCKED` para fila, JSONB, índices parciais |
| ORM/migrations | SQLAlchemy 2.0 + Alembic | padrão, tipado, migrations versionadas |
| Fila/cache | Redis 7 | locks por conta, códigos 2FA de curta duração, rate limit |
| Worker | arq | asyncio, integra com FastAPI, cron embutido, leve |
| Arquivos | storage S3-compatível (MinIO local; S3/R2 em prod) | uploads/downloads fora do banco, URLs pré-assinadas |
| Cripto | `cryptography` (Fernet ou AES-GCM) | credenciais/sessão criptografadas em repouso |

Alternativa aceitável: Celery no lugar do arq se o time já opera Celery.
O desenho de fila abaixo não depende da lib de worker.

Observação sobre o `instagrapi`: ele é **síncrono** (`requests`). Dentro dos
jobs, chamadas ao client rodam via `asyncio.to_thread`, com pool limitado.
Nunca chamar o client dentro do event loop da API.

## 3. Estrutura de pastas proposta

```
backend/
├── app/
│   ├── main.py                 # cria FastAPI, monta routers
│   ├── core/
│   │   ├── config.py           # Settings (pydantic-settings)
│   │   ├── security.py         # JWT, hash de senha/API key
│   │   ├── crypto.py           # encrypt/decrypt de campos sensíveis
│   │   └── logging.py          # logs estruturados com redaction
│   ├── db/
│   │   ├── base.py             # Base, session factory
│   │   ├── models/             # tenant, user, account, job, webhook...
│   │   └── migrations/         # Alembic
│   ├── api/
│   │   ├── deps.py             # auth, tenant, RBAC, paginação
│   │   └── v1/                 # auth, accounts, jobs, media, insights, webhooks
│   ├── services/
│   │   ├── ig_gateway.py       # wrapper do instagrapi (testável)
│   │   ├── accounts.py         # ciclo de vida de conta/sessão
│   │   ├── jobs.py             # enfileirar, claim, retry
│   │   └── storage.py          # S3
│   ├── jobs/                   # handlers por tipo de job
│   ├── workers/
│   │   ├── worker.py           # arq WorkerSettings
│   │   └── dispatcher.py       # jobs do banco -> fila
│   └── schemas/                # Pydantic request/response
├── scripts/
│   ├── dev.sh                  # api + worker + cron
│   └── create_admin.py
├── docker-compose.yml          # postgres, redis, minio
├── Dockerfile
└── tests/
    ├── unit/
    └── integration/
```

O `funcs/` atual continua sendo a camada de operações. O backend **não**
duplica lógica do Instagram: os jobs importam `funcs.*` e injetam o client
da conta. A única exceção é o login, que precisa do `Client` cru para
controlar 2FA e exportar a sessão.

## 4. Modelo de dados

Todas as tabelas de domínio carregam `tenant_id` e têm soft delete
(`deleted_at`) onde faz sentido. FKs com `ON DELETE RESTRICT` para não perder
rastro; exclusão de tenant é operação administrativa.

### tenants
`id uuid pk`, `name`, `slug unique`, `plan`, `created_at`, `updated_at`.

### users
`id uuid pk`, `tenant_id fk`, `email`, `password_hash` (Argon2id),
`role` (`owner|admin|operator|viewer`), `is_active`, `last_login_at`,
`created_at`. Índice único `(tenant_id, lower(email))`.

### api_keys
`id`, `tenant_id`, `user_id nullable`, `name`, `key_prefix`, `key_hash`,
`scopes text[]`, `last_used_at`, `revoked_at`, `created_at`.
Chave exibida uma única vez (`ik_live_<prefix>_<secret>`); guardar só o hash.

### ig_accounts
```
id uuid pk
tenant_id fk
label text
username text
password_enc bytea            -- criptografado
proxy_enc bytea null          -- criptografado (contém credenciais)
device_settings_enc jsonb     -- uuid, device, app version, locale, tz
session_enc jsonb null        -- settings do instagrapi após login
status text                   -- ver máquina de estados
last_error_code text null
last_error_message text null  -- sanitizado, sem credenciais
last_login_at timestamptz null
last_health_at timestamptz null
created_at, updated_at, deleted_at
```
Índices: `unique (tenant_id, lower(username)) where deleted_at is null`;
`(tenant_id, status)`.

**`device_settings_enc` é obrigatório e é gerado uma vez na criação da conta.**
Reutilizar o mesmo perfil de dispositivo em todas as tentativas evita que o
Instagram trate cada login como um aparelho novo. Sem isso, o volume de
checkpoints sobe muito.

### login_attempts
```
id uuid pk
account_id fk
status text            -- pending_2fa|succeeded|failed|expired|challenge_required
method text null       -- sms|totp|backup_code|unknown
attempts int default 0 -- tentativas de código (máx. 3)
expires_at timestamptz -- agora + 10 min para pending_2fa
error_code text null
created_at, finished_at
```
O código em si **não** é gravado aqui (ver §6).

### jobs
```
id uuid pk
tenant_id fk
account_id fk null
type text
payload jsonb
status text            -- queued|running|awaiting_input|succeeded|failed|canceled
priority smallint default 5
run_after timestamptz default now()
attempts smallint default 0
max_attempts smallint default 3
result jsonb null
error_code text null
error_message text null
idempotency_key text null
created_by uuid null
locked_by text null    -- worker id
locked_at timestamptz null
started_at, finished_at, created_at
```
Índices:
- `(status, run_after, priority)` para o dispatcher.
- `(tenant_id, created_at desc)` para listagem.
- **`unique (account_id) where status = 'running'`** — garante no banco que
  uma conta executa no máximo um job por vez. É o coração da serialização.
- `unique (tenant_id, idempotency_key) where idempotency_key is not null`.

### media_assets
`id`, `tenant_id`, `account_id`, `media_pk`, `kind`, `storage_key`,
`size_bytes`, `content_type`, `created_at`; índice único
`(account_id, media_pk, kind)`.

### webhook_endpoints / webhook_deliveries
Endpoint: `id`, `tenant_id`, `url`, `secret_enc`, `events text[]`, `is_active`.
Delivery: `id`, `endpoint_id`, `event`, `payload jsonb`, `status`,
`attempts`, `next_attempt_at`, `response_status`, `created_at`.

### audit_logs
`id`, `tenant_id`, `user_id`, `action`, `account_id null`, `metadata jsonb`
(sem segredos), `ip`, `created_at`.

## 5. Estados

**Conta**
```
pending_login ──login ok──────────────► active
      │                                   │
      ├──2FA exigido──► 2fa_required      ├──sessão rejeitada──► needs_reauth
      │                     │             ├──checkpoint────────► challenge_required
      │                     └─código ok──►│
      └──senha errada/erro terminal──► needs_reauth
```
- `pending_login`: criada, login nunca concluído.
- `active`: sessão válida salva.
- `2fa_required`: aguardando código; `login_attempts.expires_at` manda.
- `challenge_required`: ação humana no app necessário. Não expira sozinho;
  só sai via `POST /accounts/{id}/login` depois da resolução manual.
- `needs_reauth`: senha/código errado ou sessão inválida sem relogin possível.
- `disabled`: desativada pelo tenant; jobs recusados.

**Job**: `queued → running → succeeded|failed`, com `awaiting_input` para
o caso de 2FA (raro, se adotarmos o fallback da §6) e `canceled`.

## 6. Fluxo de login e 2FA

Fato verificado no `instagrapi` 3.2: `login(username, password,
verification_code=code)` refaz o CAA e resolve o segundo fator **dentro da
mesma tentativa** (`bloks_caa_login` chama `bloks_caa_resolve_two_step_verification`).
Ou seja, não é necessário manter o objeto `Client` de uma requisição anterior
na memória. O que **precisa** ser mantido é o perfil de dispositivo (§4).

### Criação da conta
1. `POST /v1/accounts` grava a conta com senha cifrada e gera
   `device_settings_enc` a partir de um `Client()` novo (`cl.get_settings()`).
2. Status `pending_login`; enfileira `account.login` (se `auto_login=true`).

### Job `account.login` (sem código)
1. Adquire o lock Redis `account:{id}` (`SET NX EX 120`) e confirma que não há
   job `running` para a conta (índice parcial).
2. `Client()`, aplica `device_settings`, proxy, `delay_range=[1,3]`.
3. `cl.login(username, decrypt(password))`.
4. Resultado:
   - `True` → salva `session_enc = encrypt(cl.get_settings())`,
     `last_login_at=now()`, status `active`; attempt `succeeded`.
   - `TwoFactorRequired` → status `2fa_required`; cria `login_attempts` com
     `pending_2fa`, `expires_at=now()+10min`, `method` inferido do contexto;
     emite evento `account.2fa_required`; attempt `pending_2fa`.
   - `ChallengeRequired` / checkpoint → status `challenge_required`;
     mensagem clara de que é preciso resolver no app; **sem retry**.
   - `BadPassword` → status `needs_reauth`; sem retry.
   - erro de rede/5xx → attempt `failed`, job `queued` com backoff
     (3 tentativas, jitter), mantendo status atual.
5. Libera lock.

### `POST /v1/accounts/{id}/2fa`
1. Valida dono/tenant, status `2fa_required`, attempt pendente não expirado.
2. Publica o código em Redis: `2fa:{account_id}` com TTL até `expires_at`.
   O código não vai para o banco, logs, audit nem webhooks.
3. Enfileira `account.login_2fa` com `attempt_id` (não com o código) e
   responde `202 Accepted`.
4. Worker lê o código do Redis (e apaga) e roda `login(..., verification_code=code)`
   com o mesmo `device_settings`.
5. Sucesso → sessão salva, status `active`.
   Falha por código inválido → incrementa `attempts`; se `attempts < 3`,
   volta para `2fa_required` com novo `expires_at`; senão `needs_reauth`.
6. **Fallback** (só se a tentativa nova rejeitar um código válido): o mesmo job
   mantém o `Client` em memória e tenta uma vez mais nele. Isso exige que o job
   não seja interrompido; por isso o job de login tem fila própria e
   `max_attempts=1` no nível de fila (o retry de código é interno).

### Restauração de sessão (caminho normal depois do primeiro login)
```
cl = Client()
cl.set_settings(decrypt(session_enc))
cl.login(username, decrypt(password))   # valida via account_info()
if LoginRequired -> o próprio login() faz relogin (pode exigir 2FA de novo)
session_enc = encrypt(cl.get_settings())  # só se mudou
```
Atenção: `load_settings`/`set_settings` de perfis de app diferentes pode exigir
`override_app_version=True`; fixar a versão do app no perfil de dispositivo.
Sempre regravar a sessão após uso, porque cookies/claims rotacionam.

### Health check
Job diário (ou sob demanda) por conta `active`: `account_info()` leve.
`LoginRequired` → status `needs_reauth` e evento. Sem tentar relogin
automático em série: um relogin por dia no máximo, com backoff.

### Isolamento de sessão
Nunca usar a mesma conta em dois workers. O lock Redis + índice parcial de
`running` garantem isso; sessão só é gravada pelo worker que tem o lock.
Duas sessões válidas ao mesmo tempo costumam derrubar uma delas e gerar
checkpoint.

## 7. API v1

Autenticação: JWT (access 15 min, refresh 30 dias, refresh rotativo) ou
API key. Todo recurso é escopado pelo `tenant_id` do token. Nunca aceitar
`tenant_id` vindo do corpo/query.

### Auth
| Método | Rota | Descrição |
|---|---|---|
| POST | `/v1/auth/register` | cria tenant + owner (invite-only em prod) |
| POST | `/v1/auth/token` | login, retorna access + refresh |
| POST | `/v1/auth/refresh` | troca refresh por novo par |
| POST | `/v1/auth/logout` | revoga refresh |
| GET | `/v1/me` | usuário e tenant atuais |
| GET/POST/DELETE | `/v1/api-keys[/{id}]` | gestão de chaves |

### Contas
| Método | Rota | Descrição |
|---|---|---|
| GET | `/v1/accounts` | lista com filtro `status` e paginação por cursor |
| POST | `/v1/accounts` | `{label, username, password, proxy?, auto_login?}` |
| GET | `/v1/accounts/{id}` | dados públicos + status (nunca senha/sessão) |
| PATCH | `/v1/accounts/{id}` | label, proxy, senha (força `needs_reauth`) |
| DELETE | `/v1/accounts/{id}` | soft delete + logout best-effort |
| POST | `/v1/accounts/{id}/login` | inicia/reinicia login |
| POST | `/v1/accounts/{id}/2fa` | `{code}` para o login pendente |
| POST | `/v1/accounts/{id}/logout` | descarta sessão local e tenta logout |
| GET | `/v1/accounts/{id}/health` | valida a sessão agora (síncrono, curto) |
| GET | `/v1/accounts/{id}/login-attempts` | histórico sem códigos |

### Jobs e operações
| Método | Rota | Descrição |
|---|---|---|
| POST | `/v1/accounts/{id}/jobs` | `{type, payload, priority?, run_after?, idempotency_key?}` |
| GET | `/v1/jobs` | filtros por conta, tipo, status |
| GET | `/v1/jobs/{id}` | status, resultado, erro sanitizado |
| POST | `/v1/jobs/{id}/cancel` | só se `queued` |
| GET | `/v1/accounts/{id}/media` | leitura síncrona cacheada |
| GET | `/v1/accounts/{id}/insights` | último snapshot |
| POST | `/v1/accounts/{id}/insights/sync` | enfileira atualização |

Status HTTP: `202` para tudo que vira job, `409` para conflito de estado
(ex.: 2FA quando não é esperado), `422` para payload inválido, `429` para
quota/rate limit. Erros com `code` estável (`account_challenge_required`,
`account_needs_reauth`, `job_conflict`, `quota_exceeded`) para o cliente
programar em cima.

Paginação por cursor (`created_at,id`), nunca offset em tabelas grandes.
Toda resposta inclui `request_id`; listagens incluem `next_cursor`.

### Payloads de jobs (v1)
```
account.login            {}
account.login_2fa        {}            # código vem do Redis, não do payload
account.health           {}
account.logout           {}
media.list               {username?, amount?}
media.download           {media_pk|url, kinds?: ["photo","video"]}
publish.photo            {storage_key, caption?, schedule_at?}
publish.video            {storage_key, caption?, thumbnail_key?}
publish.reel             {storage_key, caption?, thumbnail_key?}
publish.album            {storage_keys[], caption?}
publish.story            {storage_key, kind: "photo"|"video"}
insights.account         {}
insights.feed            {period?, amount?}
direct.send_text         {usernames?|thread_id, text}
```
Cada handler valida o payload com schema próprio e mapeia para o `funcs.*`
correspondente. Publicação é a operação mais delicada: ver idempotência em §8.

## 8. Filas, concorrência e confiabilidade

Modelo: **Postgres é a fonte da verdade; Redis/arq é só transporte.**

- **Dispatcher** (processo cron, a cada 1–2 s): `SELECT ... FOR UPDATE
  SKIP LOCKED` pegando jobs `queued` com `run_after <= now()`, cuja conta não
  tenha job `running`, e empurra para o arq. O índice único parcial é a
  garantia final contra duas execuções concorrentes da mesma conta.
- **Worker** de execução: adquire lock Redis `account:{id}` com TTL renovado
  durante o job, marca `running` + `locked_by/locked_at`, executa, grava
  resultado e libera.
- **Sweeper** (cron 1 min): jobs `running` com `locked_at` antigo (processo
  morreu) voltam para `queued` com `attempts += 1`; lock Redis órfão expira.
- **Cron**: health check diário por conta, retry de webhooks, limpeza de
  `login_attempts` expirados.

Serialização por conta significa que throughput é **por conta**, não global.
Duas contas rodam em paralelo; a mesma conta, uma operação por vez. Isso é
proposital: é o que mantém a conta viva.

Política de retry:
| Erro | Ação |
|---|---|
| timeout/5xx/429 do IG | retry com backoff exponencial + jitter, 3 tentativas |
| `LoginRequired` | 1 relogin; se exigir 2FA, vira `2fa_required` |
| `TwoFactorRequired` | não é falha: estado `2fa_required` |
| `ChallengeRequired` | terminal, sem retry |
| `BadPassword` | terminal, sem retry |
| payload inválido | falha imediata, sem retry |
| publish | **não** retry automático após envio ambíguo; ver abaixo |

Idempotência:
- `idempotency_key` única por tenant para POSTs de job.
- Publicação: antes de enviar, o job grava `attempt` com estado `sending`; ao
  receber `media_pk`, grava no `result`. Se o processo morrer entre o envio e a
  resposta, o job fica `failed` com `error_code=ambiguous_publish` e **não**
  repete sozinho — o cliente confirma na conta (ou o job de reconciliação
  procura o post) antes de qualquer reenvio. Post duplicado é pior que post
  faltando.
- Downloads: idempotentes por `(account_id, media_pk, kind)`.

Rate limit e quotas:
- Por conta: 1 job simultâneo (banco), `delay_range` no client, intervalo
  mínimo entre jobs da mesma conta (ex.: 2 s) via `run_after`.
- Por tenant/plano: nº de contas, jobs/dia, tipos de job permitidos.
- Rate limit HTTP por API key (Redis token bucket), `429` com `Retry-After`.
- Limite global de requisições ao IG por processo para não saturar proxy/IP.

## 9. Storage de arquivos

- Upload: `POST /v1/uploads` retorna URL pré-assinada (PUT) + `storage_key`.
  O job de publicação recebe apenas `storage_key`.
- Download: job baixa para um tempdir, envia ao bucket e grava `media_assets`;
  a API entrega URL pré-assinada de curta duração (`GET /v1/media/{id}`).
- Não usar o disco do worker como armazenamento durável.
- Tamanho máximo e content-type validados no presign e revalidados no job.

## 10. Segurança

- Senhas de usuários: Argon2id. Senhas do Instagram, proxy e settings de
  sessão: criptografia simétrica autenticada, com `key_id` no prefixo do
  ciphertext para permitir rotação (envelope/KMS em produção; chave em secret
  manager, nunca no `.env` de produção nem no repositório).
- API keys com hash SHA-256 + prefixo indexável; exibidas só na criação.
- JWT: segredo separado, `aud`/`iss`, access curto, refresh rotativo com
  detecção de reuso (família de tokens revogada).
- RBAC: `viewer` lê, `operator` cria jobs, `admin` gerencia contas/API keys,
  `owner` gerencia membros e o tenant.
- Isolamento: toda query parte de um repositório que exige `tenant_id`;
  teste automatizado que tenta acessar conta de outro tenant e espera 404.
  RLS do Postgres como defesa em profundidade (fase 5).
- 2FA: código só em Redis, TTL curto, uso único, apagado ao consumir;
  nunca em log, audit, webhook ou resposta. Comparação não precisa de hash
  (é um segredo efêmero e a origem é o usuário), mas não pode ser logado.
- Logs: redaction de `password`, `verification_code`, `session`, `proxy`,
  cookies, headers de authorization. Respostas cruas do IG podem conter PII:
  guardar só `code/message` sanitizados.
- CORS restrito, TLS obrigatório, sem stack trace em produção.
- Auditoria de: criação/exclusão de conta, troca de senha/proxy, login/logout,
  geração/revogação de API key, criação de job sensível.

## 11. Observabilidade e operação

- Logs JSON com `request_id`, `tenant_id`, `account_id`, `job_id`, `type`,
  `status`, `duration_ms`.
- Métricas Prometheus: `jobs_total{type,status}`, `job_duration_seconds`,
  `queue_depth{priority}`, `accounts_by_status`, `login_failures_total{reason}`,
  `ig_http_errors_total{status}`, `webhook_delivery_failures_total`.
- Alertas: pico de `challenge_required`, fila crescendo por > X min, taxa de
  falha de login acima do baseline, worker sem heartbeat.
- Sentry para exceções, com scrub de segredos.
- `GET /healthz` (liveness, sem dependências) e `GET /readyz` (banco/Redis).
- Deploy: `alembic upgrade head` antes de subir a nova versão da API; workers
  com shutdown gracioso (parar de pegar jobs, terminar o atual).
- Local: `docker compose up` com Postgres, Redis e MinIO; API, worker e
  dispatcher em processos separados.

## 12. Riscos e limites

- **ToS e banimento**: API privada não oficial. Contas podem ser restringidas
  a qualquer momento. Isolar contas por proxy, manter volume baixo e não
  prometer estabilidade no produto.
- **Checkpoint**: pode exigir verificação no app oficial, que o backend não
  consegue automatizar. O produto precisa de UX para esse estado.
- **Sessão**: uma sessão por conta; qualquer automação concorrente fora do
  backend (app no celular, outro script) pode invalidar a sessão.
- **Escala**: limite real é por conta e por IP/proxy, não por CPU. Adicionar
  workers não aumenta o throughput de uma conta.
- **2FA por TOTP**: hoje o plano assume código fornecido pelo usuário. Guardar
  o seed TOTP para gerar códigos automaticamente é possível (`pyotp`), mas
  aumenta o impacto de vazamento e fica como decisão separada.
- **Custo**: proxy residencial/móvel por conta é o maior custo operacional.

## 13. Fases de implementação

Cada fase entrega algo verificável sozinho.

**Fase 1 — Fundação**
Repo `backend/`, config, docker compose, modelos tenant/user/account,
Alembic, JWT + API keys, RBAC básico, CRUD de contas com cripto e
`device_settings`, testes de isolamento entre tenants.
Pronto quando: dois tenants não se enxergam e segredos estão cifrados no banco.

**Fase 2 — Login e 2FA (núcleo)**
`ig_gateway` (wrapper testável), job `account.login`, endpoint `/2fa`,
persistência/restauração de sessão, health check, máquina de estados e
eventos de status, fake do instagrapi para testes.
Pronto quando: os cenários login ok / 2FA / código errado / challenge / sessão
inválida passam contra o fake e um teste manual com conta real conclui o login.

**Fase 3 — Jobs e leitura**
Dispatcher com `SKIP LOCKED`, worker arq, locks, sweeper, retry/backoff,
jobs API, `media.list`, `media.download`, `insights.account`, storage S3,
`media_assets`.
Pronto quando: dois jobs concorrentes da mesma conta são serializados e um
worker morto no meio é recuperado pelo sweeper.

**Fase 4 — Publicação e webhooks**
Uploads pré-assinados, `publish.*` com proteção de post ambíguo, webhooks
com HMAC + retry, audit log.
Pronto quando: job de publicação publica uma vez e um timeout simulado não
gera post duplicado.

**Fase 5 — Endurecimento**
Quotas por plano, rate limit por chave, métricas e alertas, rotação de chave,
RLS, runbooks (challenge, sessão inválida, fila travada), teste de carga do
dispatcher.

## 14. Testes

- **Unitários**: cripto/rotação, hash, RBAC, máquinas de estado, política de
  retry, sanitização de erros, idempotência.
- **Integração**: Postgres/Redis reais (compose ou testcontainers), API com
  `dependency_overrides` trocando o `ig_gateway` por fake. Cobrir: login ok,
  2FA ok, 2FA expirado, 3 códigos errados, challenge, sessão inválida,
  isolamento entre tenants, concorrência da mesma conta, job órfão.
- **Contrato com o IG real**: manual, com conta de teste, fora do CI.
  Nunca commitar credenciais nem `session.json`.
- **Carga**: dispatcher e claim concorrente (dois dispatchers) sem job
  duplicado; verificar o índice parcial sob concorrência.

## 15. Decisões abertas

1. **TOTP seed**: aceitar só código de uso único ou também guardar o seed e
   gerar códigos automaticamente? (recomendo começar só com código).
2. **Worker**: arq (recomendado) ou Celery por familiaridade do time?
3. **Quotas**: limites por plano (contas, jobs/dia) e o que fazer ao estourar.
4. **Proxy**: provedor, rotação, e se o proxy é por conta ou compartilhado
   (recomendo obrigatório por conta em qualquer escala real).
5. **Tenancy**: um usuário pode pertencer a vários tenants? (o modelo com
   `users.tenant_id` assume 1; membership N:N é fácil de migrar depois).
6. **API oficial**: manter um adapter alternativo para contas business ou
   descartar por enquanto.
7. **Reconciliação de publicação ambígua**: procurar o post por legenda/timestamp
   automaticamente ou exigir confirmação do cliente?
