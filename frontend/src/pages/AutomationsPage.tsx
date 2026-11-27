import {
  Copy,
  Pause,
  Pencil,
  Play,
  Plus,
  Search,
  Trash2,
  Workflow,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { EmptyState, PageHeader, Spinner } from "../components/ui";
import { useToast } from "../toast";
import type { Flow, FlowRun } from "../types";
import { formatShortDate, relativeTime } from "../utils";

type Status = "ativa" | "pausada" | "rascunho";
type Filter = "todas" | Status;

function statusOf(flow: Flow, runs: FlowRun[]): Status {
  if (flow.enabled) return "ativa";
  return runs.length ? "pausada" : "rascunho";
}

export function AutomationsPage() {
  const { notify } = useToast();
  const [flows, setFlows] = useState<Flow[]>([]);
  const [runs, setRuns] = useState<Record<string, FlowRun[]>>({});
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<Filter>("todas");
  const [categoryFilter, setCategoryFilter] = useState("todas");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.flows();
      const entries = await Promise.all(
        list.map(async (flow) => [flow.id, await api.flowRuns(flow.id, 50)] as const),
      );
      setFlows(list);
      setRuns(Object.fromEntries(entries));
    } catch (err) {
      notify(
        err instanceof ApiError ? err.message : "Falha ao carregar automações.",
        "error",
      );
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const categories = useMemo(
    () => ["todas", ...new Set(flows.map((flow) => flow.category))],
    [flows],
  );

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return flows.filter((flow) => {
      const status = statusOf(flow, runs[flow.id] ?? []);
      const matchesTerm =
        !term ||
        flow.name.toLowerCase().includes(term) ||
        (flow.description ?? "").toLowerCase().includes(term);
      const matchesStatus = statusFilter === "todas" || status === statusFilter;
      const matchesCategory =
        categoryFilter === "todas" || flow.category === categoryFilter;
      return matchesTerm && matchesStatus && matchesCategory;
    });
  }, [flows, runs, search, statusFilter, categoryFilter]);

  async function toggle(flow: Flow) {
    setBusy(flow.id);
    try {
      await api.updateFlow(flow.id, { enabled: !flow.enabled });
      notify(flow.enabled ? "Automação pausada." : "Automação ativada.", "success");
      await load();
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Falha ao alterar status.", "error");
    } finally {
      setBusy(null);
    }
  }

  async function duplicate(flow: Flow) {
    setBusy(flow.id);
    try {
      await api.createFlow({
        name: `Cópia de ${flow.name}`.slice(0, 120),
        description: flow.description,
        category: flow.category,
        graph: flow.graph,
        enabled: false,
        trigger_source: flow.trigger_source,
        account_id: flow.account_id,
        poll_interval_seconds: flow.poll_interval_seconds,
      });
      notify("Automação duplicada como rascunho.", "success");
      await load();
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Falha ao duplicar.", "error");
    } finally {
      setBusy(null);
    }
  }

  async function remove(flow: Flow) {
    if (!window.confirm(`Excluir a automação "${flow.name}"?`)) return;
    setBusy(flow.id);
    try {
      await api.deleteFlow(flow.id);
      notify("Automação excluída.", "success");
      await load();
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Falha ao excluir.", "error");
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <Spinner label="Carregando automações" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Workspace"
        title="Automações"
        description="Gerencie seus fluxos, status e execuções em um só lugar."
        actions={
          <Link className="button button-primary" to="/flows">
            <Plus size={16} />
            Nova automação
          </Link>
        }
      />

      <div className="toolbar">
        <div className="search-box">
          <Search size={16} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nome ou descrição"
          />
        </div>
        <label className="select-field">
          Status
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as Filter)}
          >
            <option value="todas">Todas</option>
            <option value="ativa">Ativas</option>
            <option value="pausada">Pausadas</option>
            <option value="rascunho">Rascunhos</option>
          </select>
        </label>
        <label className="select-field">
          Categoria
          <select
            value={categoryFilter}
            onChange={(event) => setCategoryFilter(event.target.value)}
          >
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </label>
        <span className="toolbar-count">
          {visible.length} de {flows.length}
        </span>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={Workflow}
          title="Nenhuma automação encontrada"
          description={
            flows.length
              ? "Ajuste os filtros ou a busca."
              : "Crie seu primeiro fluxo no construtor visual."
          }
          action={
            !flows.length ? (
              <Link className="button button-primary" to="/flows">
                Criar automação
              </Link>
            ) : undefined
          }
        />
      ) : (
        <div className="automation-grid">
          {visible.map((flow) => {
            const flowRuns = runs[flow.id] ?? [];
            const status = statusOf(flow, flowRuns);
            const last = flowRuns[0];
            return (
              <article key={flow.id} className="panel automation-card">
                <div className="automation-card-head">
                  <div>
                    <h3>{flow.name}</h3>
                    <span className="category-tag">{flow.category}</span>
                  </div>
                  <span className={`status status-${status}`}>{status}</span>
                </div>
                <p className="automation-description">
                  {flow.description || "Sem descrição."}
                </p>
                <dl className="automation-meta">
                  <div>
                    <dt>Execuções</dt>
                    <dd>{flowRuns.length}</dd>
                  </div>
                  <div>
                    <dt>Última execução</dt>
                    <dd>{last ? relativeTime(last.created_at) : "—"}</dd>
                  </div>
                  <div>
                    <dt>Criada em</dt>
                    <dd>{formatShortDate(flow.created_at)}</dd>
                  </div>
                </dl>
                <div className="automation-actions">
                  <Link
                    className="button button-ghost button-small"
                    to={`/flows?id=${flow.id}`}
                  >
                    <Pencil size={13} />
                    Editar
                  </Link>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => void toggle(flow)}
                    disabled={busy === flow.id}
                    title={flow.enabled ? "Pausar" : "Ativar"}
                    aria-label={flow.enabled ? "Pausar" : "Ativar"}
                  >
                    {flow.enabled ? <Pause size={14} /> : <Play size={14} />}
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => void duplicate(flow)}
                    disabled={busy === flow.id}
                    title="Duplicar"
                    aria-label="Duplicar"
                  >
                    <Copy size={14} />
                  </button>
                  <button
                    type="button"
                    className="icon-button icon-danger"
                    onClick={() => void remove(flow)}
                    disabled={busy === flow.id}
                    title="Excluir"
                    aria-label="Excluir"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
