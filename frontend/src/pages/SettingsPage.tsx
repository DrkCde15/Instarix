import {
  Activity,
  BarChart3,
  KeyRound,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import {
  CopyButton,
  EmptyState,
  PageHeader,
  Spinner,
  StatCard,
} from "../components/ui";
import { useToast } from "../toast";
import type { ApiKey, Usage } from "../types";
import { formatDate, formatShortDate } from "../utils";

const SCOPES = [
  "accounts:read",
  "accounts:write",
  "accounts:2fa",
  "jobs:read",
  "jobs:write",
  "keys:manage",
  "webhooks:read",
  "webhooks:write",
  "audit:read",
];

export function SettingsPage() {
  const { notify } = useToast();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [keyName, setKeyName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["jobs:read"]);
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<string | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextUsage, nextKeys] = await Promise.all([
        api.usage(),
        api.apiKeys(),
      ]);
      setUsage(nextUsage);
      setKeys(nextKeys);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Falha ao carregar configurações.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function toggleScope(scope: string) {
    setScopes((current) =>
      current.includes(scope)
        ? current.filter((item) => item !== scope)
        : [...current, scope],
    );
  }

  async function createKey(event: FormEvent) {
    event.preventDefault();
    if (!scopes.length) {
      setError("Selecione ao menos um escopo.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const created = await api.createApiKey({
        name: keyName.trim(),
        scopes,
      });
      setCreatedKey(created.key);
      setKeyName("");
      notify("API key criada. Copie a chave agora.", "success");
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Não foi possível criar a API key.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function revoke(key: ApiKey) {
    if (!window.confirm(`Revogar a API key "${key.name}"?`)) return;
    try {
      await api.revokeApiKey(key.id);
      notify("API key revogada.", "success");
      await load();
    } catch (err) {
      notify(
        err instanceof ApiError ? err.message : "Falha ao revogar API key.",
        "error",
      );
    }
  }

  async function loadMetrics() {
    setMetricsLoading(true);
    setError(null);
    try {
      setMetrics(await api.metricsText());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Falha ao carregar métricas.",
      );
    } finally {
      setMetricsLoading(false);
    }
  }

  if (loading) return <Spinner label="Carregando configurações" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Workspace"
        title="Configurações"
        description="Plano, uso, chaves de API e métricas operacionais."
      />

      {error && <div className="error-banner">{error}</div>}

      {usage && (
        <section className="stats-grid">
          <StatCard
            label="Plano"
            value={usage.plan}
            hint="limites definidos no backend"
            icon={Activity}
            accent="teal"
          />
          <StatCard
            label="Contas"
            value={`${usage.accounts_used}/${usage.accounts_limit || "∞"}`}
            hint="contas ativas no tenant"
            icon={Activity}
            accent="violet"
          />
          <StatCard
            label="Jobs hoje"
            value={`${usage.jobs_today_used}/${usage.jobs_today_limit || "∞"}`}
            hint="janela diária em UTC"
            icon={BarChart3}
            accent="amber"
          />
        </section>
      )}

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>API keys</h2>
            <p>Use no header X-API-Key. O valor completo aparece só na criação.</p>
          </div>
        </div>

        {createdKey && (
          <div className="secret-banner inline-secret">
            <div>
              <strong>Nova API key</strong>
              <code>{createdKey}</code>
            </div>
            <div className="inline-actions">
              <CopyButton value={createdKey} label="Copiar chave" />
              <button
                type="button"
                className="button button-ghost button-small"
                onClick={() => setCreatedKey(null)}
              >
                Ocultar
              </button>
            </div>
          </div>
        )}

        <form className="key-form" onSubmit={createKey}>
          <label className="field">
            <span>Nome</span>
            <input
              value={keyName}
              onChange={(event) => setKeyName(event.target.value)}
              placeholder="CI · leitura"
              required
            />
          </label>
          <div className="field">
            <span>Escopos</span>
            <div className="scope-grid">
              {SCOPES.map((scope) => (
                <label key={scope} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={scopes.includes(scope)}
                    onChange={() => toggleScope(scope)}
                  />
                  <code>{scope}</code>
                </label>
              ))}
            </div>
          </div>
          <button type="submit" className="button button-primary" disabled={creating}>
            <Plus size={15} />
            {creating ? "Criando…" : "Criar API key"}
          </button>
        </form>

        {keys.length === 0 ? (
          <EmptyState
            icon={KeyRound}
            title="Nenhuma API key"
            description="Crie uma chave com escopos mínimos para integrar serviços."
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Prefixo</th>
                  <th>Escopos</th>
                  <th>Último uso</th>
                  <th>Criada</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.id}>
                    <td>
                      <strong>{key.name}</strong>
                      {key.revoked_at && (
                        <span className="status status-canceled">revogada</span>
                      )}
                    </td>
                    <td>
                      <code>{key.key_prefix}…</code>
                    </td>
                    <td>
                      <div className="event-chips">
                        {key.scopes.map((scope) => (
                          <span key={scope}>{scope}</span>
                        ))}
                      </div>
                    </td>
                    <td className="muted">{formatShortDate(key.last_used_at)}</td>
                    <td className="muted">{formatShortDate(key.created_at)}</td>
                    <td>
                      {!key.revoked_at && (
                        <button
                          type="button"
                          className="icon-button icon-danger"
                          onClick={() => void revoke(key)}
                          aria-label="Revogar API key"
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Métricas</h2>
            <p>Snapshot Prometheus do banco, calculado na hora.</p>
          </div>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void loadMetrics()}
            disabled={metricsLoading}
          >
            <RefreshCw size={15} className={metricsLoading ? "spin" : ""} />
            Carregar métricas
          </button>
        </div>
        {metrics ? (
          <pre className="json-block metrics-block">{metrics}</pre>
        ) : (
          <p className="muted">
            Requer permissão <code>keys:manage</code>. Clique em carregar para
            consultar <code>/v1/metrics</code>.
          </p>
        )}
      </section>
    </div>
  );
}
