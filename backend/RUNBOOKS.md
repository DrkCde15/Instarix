# Runbooks — Instarix backend

## Conta em `challenge_required`

1. Não reenfileire jobs nem tente relogin automático: o checkpoint exige ação
   humana no app oficial.
2. Confirme em `GET /v1/accounts/{id}` que `status=challenge_required`.
3. Peça ao cliente para resolver a verificação no app e então chamar
   `POST /v1/accounts/{id}/login` com a mesma sessão/proxy.
4. Se o challenge voltar, reduza o volume de operações e revise o proxy.

## Conta em `needs_reauth` ou sessão inválida

1. `GET /v1/accounts/{id}` e `GET /v1/accounts/{id}/login-attempts`.
2. Verifique se a senha mudou ou se a sessão foi usada fora do backend.
3. Se a senha mudou, `PATCH /v1/accounts/{id}` com `password` e depois
   `POST /v1/accounts/{id}/login`.
4. Nunca reuse a mesma conta em outro worker/processo: uma sessão por conta.

## Fila travada ou job órfão

```bash
# jobs running antigos
SELECT id, tenant_id, account_id, type, attempts, locked_by, locked_at
FROM jobs
WHERE status = 'running' AND locked_at < now() - interval '10 minutes';

# fila por prioridade
SELECT priority, count(*) FROM jobs WHERE status = 'queued' GROUP BY priority;
```

1. O worker roda `sweep()` a cada loop. Se não houver worker ativo, suba
   `python -m app.workers.worker`.
2. Jobs `running` com `attempts < max_attempts` voltam para `queued`; no limite
   viram `failed` com `job_worker_lost`.
3. Se a fila crescer, confira `GET /v1/metrics` (`queue_depth`, `jobs_total`) e
   se o processo está consumindo. Em Postgres, valide conexões e locks:
   `SELECT * FROM pg_locks WHERE NOT granted;`.
4. A serialização é por conta: aumentar workers não acelera uma conta isolada.

## Publicação ambígua

1. Job com `error_code=ambiguous_publish` **não** é repetido automaticamente.
2. Confira manualmente o perfil da conta antes de reenfileirar.
3. Reenviar com a mesma `idempotency_key` retorna o job existente; para tentar
   de novo, use uma chave nova depois de confirmar que não houve post.

## Webhooks falhando

1. `GET /v1/webhooks/{id}/deliveries` mostra status, tentativas e HTTP status.
2. Teste o endpoint e valide o HMAC:
   `sha256=HMAC(secret, timestamp + "." + body)` nos headers
   `X-Instarix-Timestamp`/`X-Instarix-Signature`.
3. Entregas esgotadas ficam `failed`; não há reentrega manual automática.
   Corrija o endpoint e recrie o webhook se necessário.
4. Acompanhe `webhook_delivery_failures_total` em `/v1/metrics`.

## Rotação de chaves (`SECRETS_KEYS`)

1. Gere uma chave Fernet nova e coloque-a **no início** de `SECRETS_KEYS`
   (as antigas continuam descriptografando).
2. Reinicie API/worker.
3. Rode `python -m scripts.rotate_secrets`; ele re-cifra senhas, proxies,
   `device_settings`, sessões e segredos de webhook com a chave primária.
4. Quando o script reportar zero, remova as chaves antigas e reinicie.
5. Faça backup antes; não remova uma chave ainda referenciada por ciphertext.

## Quotas

- `GET /v1/usage` mostra plano, contas usadas/limite e jobs do dia.
- `429 quota_exceeded` ao criar conta/job: ajuste o plano do tenant
  (`tenants.plan`) ou aguarde a virada do dia UTC para jobs.
- Limites em `QUOTA_*` no ambiente; `0` significa ilimitado.

## Rate limit por API key

- `429 api_key_rate_limited` com `Retry-After`; o estado é em memória por
  processo. Com várias instâncias, o limite efetivo é multiplicado.
- Ajuste `API_KEY_RATE_LIMIT`/`API_KEY_RATE_WINDOW_SECONDS`.

## Métricas e alertas

`GET /v1/metrics` (requer `keys:manage`) expõe:

- `jobs_total{type,status}`;
- `queue_depth{priority}`;
- `accounts_by_status{status}`;
- `webhook_deliveries{status}`, `webhook_delivery_failures_total`,
  `webhook_delivery_pending`.

Alertas recomendados: `challenge_required` acima do baseline, fila crescendo
por mais de 10 min, `webhook_delivery_failures_total` crescendo e worker sem
consumir (`queue_depth` estável com jobs entrando).

## RLS no PostgreSQL (opt-in)

O RLS não vem ativo por padrão. Para ativar:

1. Garanta um role separado para o worker com `BYPASSRLS` (ele precisa ver jobs
   de todos os tenants).
2. Rode `python -m scripts.enable_rls --apply` com o role dono das tabelas;
   isso ativa `FORCE ROW LEVEL SECURITY` e cria a policy `tenant_isolation`.
3. Defina `RLS_ENABLED=true` na API e reinicie. A API injeta
   `app.tenant_id` por transação; sem esse GUC as policies não retornam linhas.
4. Valide com dois tenants: o segundo deve ver 404/vazio para recursos do
   primeiro. O SQLite dos testes não suporta RLS.
5. Para desativar: `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` nas tabelas e
   `RLS_ENABLED=false`.

## Teste de carga do dispatcher

Em Postgres, com um tenant/conta de teste:

```bash
python -m scripts.load_dispatcher \
  --tenant-id <uuid> --account-id <uuid> --jobs 200 --workers 4 --cleanup
```

O comando falha se detectar job reivindicado duas vezes ou job não reivindicado.
Ele mede apenas o claim; não chama o Instagram.
