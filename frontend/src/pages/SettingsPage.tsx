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
  { value: "accounts:read", label: "Ver contas" },
  { value: "accounts:write", label: "Alterar contas" },
  { value: "accounts:2fa", label: "Confirmar código 2FA" },
  { value: "jobs:read", label: "Ver tarefas" },
  { value: "jobs:write", label: "Criar tarefas" },
  { value: "keys:manage", label: "Gerenciar chaves" },
  { value: "webhooks:read", label: "Ver integrações" },
  { value: "webhooks:write", label: "Gerenciar integrações" },
  { value: "audit:read", label: "Ver histórico" },
];

function scopeLabel(value: string): string {
  return SCOPES.find((item) => item.value === value)?.label ?? value;
}

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
      notify("Chave criada. Copie o valor agora.", "success");
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Não foi possível criar a chave.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function revoke(key: ApiKey) {
    if (!window.confirm(`Revogar a chave "${key.name}"?`)) return;
    try {
      await api.revokeApiKey(key.id);
      notify("Chave revogada.", "success");
      await load();
    } catch (err) {
      notify(
        err instanceof ApiError ? err.message : "Falha ao revogar a chave.",
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
        err instanceof ApiError ? err.message : "Falha ao carregar os indicadores.",
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
        description="Plano, uso, chaves de acesso e indicadores da operação."
      />

      {error && <div className="error-banner">{error}</div>}

      {usage && (
        <section className="stats-grid">
          <StatCard
            label="Plano"
            value={usage.plan}
            hint="limites do seu plano"
            icon={Activity}
            accent="teal"
          />
          <StatCard
            label="Contas"
            value={`${usage.accounts_used}/${usage.accounts_limit || "∞"}`}
            hint="contas conectadas"
            icon={Activity}
            accent="violet"
          />
          <StatCard
            label="Tarefas hoje"
            value={`${usage.jobs_today_used}/${usage.jobs_today_limit || "∞"}`}
            hint="renovado a cada dia"
            icon={BarChart3}
            accent="amber"
          />
        </section>
      )}

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Chaves de acesso</h2>
            <p>Use para conectar outros sistemas. Copie o valor agora: ele não aparecerá novamente.</p>
          </div>
        </div>

        {createdKey && (
          <div className="secret-banner inline-secret">
            <div>
              <strong>Nova chave de acesso</strong>
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
                <label key={scope.value} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={scopes.includes(scope.value)}
                    onChange={() => toggleScope(scope.value)}
                  />
                  <span>
                    <strong>{scope.label}</strong>
                    <code>{scope.value}</code>
                  </span>
                </label>
              ))}
            </div>
          </div>
          <button type="submit" className="button button-primary" disabled={creating}>
            <Plus size={15} />
            {creating ? "Criando…" : "Criar chave"}
          </button>
        </form>

        {keys.length === 0 ? (
          <EmptyState
            icon={KeyRound}
            title="Nenhuma chave de acesso"
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
                          <span key={scope} title={scope}>
                            {scopeLabel(scope)}
                          </span>
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
                          aria-label="Revogar chave"
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
            <h2>Indicadores</h2>
            <p>Números da operação, calculados na hora.</p>
          </div>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void loadMetrics()}
            disabled={metricsLoading}
          >
            <RefreshCw size={15} className={metricsLoading ? "spin" : ""} />
            Carregar indicadores
          </button>
        </div>
        {metrics ? (
          <pre className="json-block metrics-block">{metrics}</pre>
        ) : (
          <p className="muted">
            Disponível para quem pode gerenciar chaves. Clique em carregar para
            ver os indicadores.
          </p>
        )}
      </section>
    </div>
  );
}
