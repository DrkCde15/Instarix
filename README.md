# Instarix

API multi-tenant para operar contas do Instagram e painel web para acompanhar
contas, fila de jobs, publicação, webhooks e auditoria.

O projeto é dividido em dois pacotes:

- **`backend/`** — API FastAPI, worker de jobs, PostgreSQL, autenticação, cripto
  de credenciais, filas, uploads, webhooks e métricas.
- **`frontend/`** — SPA em React + TypeScript que consome a API v1.

> A automação usa o `instagrapi`, uma biblioteca não oficial da API privada do
> Instagram. Contas, proxies e desafios podem ser restringidos pela Meta. Use
> apenas com contas próprias, testes ou automação controlada; prefira as APIs
> oficiais em produção.

## Stack

| Camada | Tecnologias |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL |
| Autenticação | JWT de acesso em memória + refresh rotativo em cookie httpOnly, API keys, Argon2id |
| Criptografia | Fernet para senhas, sessões e segredos de webhook |
| Jobs | Fila no PostgreSQL com worker próprio, sem Redis nesta fase |
| Frontend | React 19, TypeScript, Vite 6, React Router 7 |
| Integração | `instagrapi`, webhooks HMAC-SHA256 com retry |

## Segurança

- Todas as consultas — inclusive as métricas Prometheus — filtram por
  `tenant_id`; IDs de outro tenant respondem `404`.
- O refresh token é rotativo, com lock transacional e detecção de reuso que
  revoga a família. O navegador recebe o refresh em cookie `HttpOnly, Secure`
  (configurável) e mantém o access token apenas em memória.
- Webhooks validam a URL e resolvem o DNS antes de cada envio, recusando IPs
  privados/loopback e redirects. Proxies de conta também recusam hosts privados
  fora de desenvolvimento.
- `X-Forwarded-For` só é considerado com `TRUST_PROXY_HEADERS=true`, para uso
  atrás de um proxy reverso controlado.
- Uploads são validados por extensão, `Content-Type` e magic bytes.
- `backend/tests/test_migrations.py` compara o schema gerado pelo Alembic com
  os modelos SQLAlchemy para detectar drift.

## Estrutura

```text
backend/
├── app/api/          rotas HTTP (v1)
├── app/core/         config, segurança, permissões e erros
├── app/db/           modelos, sessão e migrations Alembic
├── app/services/     regras de negócio e gateway do Instagram
├── app/workers/      worker da fila
├── tests/            suíte pytest com SQLite e fakes
├── scripts/          rotação de chaves, RLS e carga
├── Dockerfile
└── README.md         setup, API, variáveis e limitações

frontend/
├── src/pages/        telas do painel
├── src/components/   layout e componentes compartilhados
├── src/api.ts        cliente HTTP, refresh, upload e download
└── README.md         setup, rotas e limitações
```

## Rodando o backend

Pré-requisitos: Python 3.12 e PostgreSQL. Os testes usam SQLite e não precisam
de banco externo.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
# Preencha DATABASE_URL, JWT_SECRET e SECRETS_KEYS.

alembic upgrade head
uvicorn app.main:app --reload
```

A API fica em `http://localhost:8000`, com documentação em `/docs`.

Em outro terminal, suba o worker que processa a fila:

```bash
cd backend
source .venv/bin/activate
python -m app.workers.worker
```

Em desenvolvimento, defina `EMBEDDED_WORKER_ENABLED=true` no `.env` para o
próprio Uvicorn processar a fila e dispensar esse segundo terminal.

Também é possível subir API e worker com Docker:

```bash
cd backend
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export SECRETS_KEYS="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
docker compose up --build
```

Configuração completa, rotas, fluxo de login/2FA, fila e limitações estão em
[`backend/README.md`](backend/README.md). Alertas e operação estão em
[`backend/RUNBOOKS.md`](backend/RUNBOOKS.md).

### Alternativa local sem PostgreSQL

Para desenvolvimento rápido, use SQLite em vez de PostgreSQL. Não use esse
banco em produção:

No `backend/.env`, use:

```dotenv
DATABASE_URL=sqlite:///./dev.db
EMBEDDED_WORKER_ENABLED=true
```

Depois basta subir um único processo:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload
```

## Rodando o frontend

Com o backend em `http://localhost:8000`:

```bash
cd frontend
npm install
cp .env.example .env   # opcional no desenvolvimento
npm run dev
```

Abra `http://localhost:5173`. O Vite faz proxy de `/v1` para o backend local.
Detalhes de autenticação, rotas e comportamento da API estão em
[`frontend/README.md`](frontend/README.md).

## Testes e verificação

```bash
# Backend: SQLite temporário, sem rede
cd backend
.venv/bin/python -m pytest -q

# Frontend: typecheck + build de produção
cd frontend
npm run build
```

## Documentação

- [`backend/README.md`](backend/README.md) — setup, variáveis de ambiente, API,
  autenticação, jobs, uploads, webhooks e segurança.
- [`backend/RUNBOOKS.md`](backend/RUNBOOKS.md) — operação, métricas e rotação de
  chaves.
- [`frontend/README.md`](frontend/README.md) — stack, rotas e limitações da SPA.
