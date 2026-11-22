# Instarix — Frontend

SPA do painel multi-tenant do Instarix, consumindo a API FastAPI em `../backend`.
Cobre autenticação, contas do Instagram (login, 2FA, sessão e histórico), fila de
jobs, publicação, webhooks, auditoria e configurações (uso, API keys e métricas).

## Stack

- React 19 + TypeScript
- Vite 6 + React Router 7
- `lucide-react` para ícones
- CSS próprio, sem framework de UI

## Rodando localmente

O backend precisa estar em `http://localhost:8000`:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload
```

Em outro terminal:

```bash
cd frontend
npm install
cp .env.example .env   # opcional no dev
npm run dev
```

Abra `http://localhost:5173`. Em desenvolvimento o Vite faz proxy de `/v1` para
`http://localhost:8000`, então não é preciso configurar CORS no backend.

### Variável de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `VITE_API_URL` | vazio | Base da API, sem barra final. Vazio usa a mesma origem e o proxy local. Em produção, defina `https://api.seu-dominio.com` ou sirva o painel atrás do mesmo domínio da API. |

## Scripts

```bash
npm run dev        # servidor de desenvolvimento
npm run typecheck  # apenas TypeScript
npm run build      # typecheck + build de produção em dist/
npm run preview    # serve o build localmente
```

## Rotas

| Rota | Tela |
|---|---|
| `/` | Visão geral: contas, fila recente e pontos de atenção |
| `/accounts` | Lista/criação de contas, com busca |
| `/accounts/:id` | Detalhe: login, 2FA, health, logout, mídia, insights, jobs e histórico |
| `/jobs` | Fila global com filtros, paginação e detalhes |
| `/publish` | Upload e enfileiramento de foto, vídeo, reel, álbum e story |
| `/webhooks` | CRUD de endpoints, segredo único e entregas |
| `/audit` | Audit log com filtro por `action` |
| `/settings` | Plano/uso, API keys e métricas Prometheus |

Rotas desconhecidas redirecionam para `/`. Em produção, configure o servidor
estático com fallback para `index.html` (SPA).

## Autenticação

- `POST /v1/auth/token`, `/v1/auth/register` e `/v1/auth/refresh` devolvem o
  access token no corpo e gravam o refresh token em cookie `HttpOnly`
  (`instarix_refresh`, `SameSite=Lax`, `Secure` em produção).
- O access token fica **apenas em memória**; o refresh token é inacessível ao
  JavaScript. O cliente usa `credentials: "include"` em todas as chamadas.
- No boot, o `AuthProvider` chama `GET /v1/me`; se houver cookie válido, a
  sessão é restaurada, senão o usuário vai para o login.
- Em um `401`, o cliente tenta `POST /v1/auth/refresh` uma vez e repete a
  requisição; requisições concorrentes compartilham o mesmo refresh.
- Se o refresh falhar, a sessão é encerrada e o evento `instarix:auth-expired`
  devolve o usuário ao login.

Como o access token vive só na memória, recarregar a página depende do cookie
httpOnly para renová-lo. O cookie usa `SameSite=Lax`; para frontend e API em
origens diferentes, configure `AUTH_COOKIE_SAMESITE=none` com `Secure` e CORS
com credenciais no backend.

## Comportamento da API

- Erros seguem `{"error": {code, message}}`; erros de validação do FastAPI
  (`detail` em lista) são convertidos em mensagem legível.
- Contas: `pending_login`, `active`, `2fa_required`, `challenge_required`,
  `needs_reauth` e `disabled`.
- `POST /v1/jobs/{id}/cancel` só funciona para jobs `queued`.
- Jobs ativos são consultados por polling (3–5 s), não por WebSocket.
- Uploads vão em multipart para `/v1/uploads`; a publicação enfileira um job
  `publish.*` com `idempotency_key` gerado no navegador.
- O segredo de webhook só aparece na criação e não pode ser recuperado.
- Downloads de mídia: o botão enfileira `media.download`; quando o job termina,
  o detalhe do job mostra os assets e permite baixar o arquivo autenticado por
  `/v1/media/{asset_id}`.

## Estrutura

```
src/
├── App.tsx              rotas e gate de autenticação
├── main.tsx             entrada React
├── api.ts               cliente HTTP, refresh via cookie, upload e download
├── auth.tsx             AuthProvider/useAuth
├── toast.tsx            notificações
├── types.ts             contratos da API
├── utils.ts             formatação de datas, status, bytes e JSON
├── styles.css           tema escuro e layout responsivo
├── components/          Layout, UI compartilhada e assets de jobs
└── pages/               uma página por rota
```

## Limitações

- Não há suíte de testes de frontend; a verificação atual é `npm run build`.
- O painel não gerencia usuários/convites do tenant; o backend é 1 usuário por
  tenant nesta fase.
- Não há WebSocket nem atualização otimista: a fila depende de polling.
- O editor de conta só altera label, senha e proxy; username não é editável.
- A listagem carrega até 100 contas/jobs por chamada; a fila e a auditoria têm
  paginação por cursor, mas a tela de contas ainda não.
