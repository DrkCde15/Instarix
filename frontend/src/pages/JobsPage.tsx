import { ListTodo, RefreshCw, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { JobAssets } from "../components/JobAssets";
import { EmptyState, PageHeader, Spinner } from "../components/ui";
import { useToast } from "../toast";
import type { Account, Job } from "../types";
import {
  formatDuration,
  formatShortDate,
  jobStatusLabel,
  jobTypeLabel,
} from "../utils";

const JOB_TYPES = [
  "media.list",
  "media.download",
  "insights.account",
  "account.health",
  "publish.photo",
  "publish.video",
  "publish.reel",
  "publish.album",
  "publish.story",
];

export function JobsPage() {
  const { notify } = useToast();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [canceling, setCanceling] = useState<string | null>(null);

  const accountLabels = useMemo(
    () => new Map(accounts.map((account) => [account.id, account])),
    [accounts],
  );

  const load = useCallback(
    async (reset = true) => {
      if (reset) setLoading(true);
      else setLoadingMore(true);
      try {
        const [page, accountPage] = await Promise.all([
          api.jobs({
            limit: 50,
            status: statusFilter || undefined,
            type: typeFilter || undefined,
            cursor: reset ? undefined : cursor ?? undefined,
          }),
          reset ? api.accounts(100) : Promise.resolve(null),
        ]);
        setJobs((current) => (reset ? page.items : [...current, ...page.items]));
        setCursor(page.next_cursor);
        setHasMore(Boolean(page.next_cursor));
        if (accountPage) setAccounts(accountPage.items);
      } catch (err) {
        notify(err instanceof ApiError ? err.message : "Falha ao carregar jobs.", "error");
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [cursor, notify, statusFilter, typeFilter],
  );

  useEffect(() => {
    void load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, typeFilter]);

  const hasActive = jobs.some(
    (job) => job.status === "queued" || job.status === "running",
  );
  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(() => void load(true), 5000);
    return () => window.clearInterval(timer);
  }, [hasActive, load]);

  async function cancel(job: Job) {
    setCanceling(job.id);
    try {
      const updated = await api.cancelJob(job.id);
      setJobs((current) => current.map((item) => (item.id === job.id ? updated : item)));
      notify("Job cancelado.", "success");
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Falha ao cancelar job.", "error");
    } finally {
      setCanceling(null);
    }
  }

  if (loading) return <Spinner label="Carregando fila" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Fila"
        title="Jobs"
        description="Acompanhe o processamento serializado por conta, resultados e erros."
        actions={
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void load(true)}
          >
            <RefreshCw size={15} />
            Atualizar
          </button>
        }
      />

      <div className="toolbar">
        <div className="filter-row">
          <label className="select-field">
            Status
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">Todos</option>
              <option value="queued">Na fila</option>
              <option value="running">Executando</option>
              <option value="succeeded">Concluídos</option>
              <option value="failed">Falhas</option>
              <option value="canceled">Cancelados</option>
            </select>
          </label>
          <label className="select-field">
            Tipo
            <select
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
            >
              <option value="">Todos</option>
              {JOB_TYPES.map((type) => (
                <option key={type} value={type}>
                  {jobTypeLabel(type)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <span className="toolbar-count">{jobs.length} jobs carregados</span>
      </div>

      {jobs.length === 0 ? (
        <EmptyState
          icon={ListTodo}
          title="Nenhum job encontrado"
          description="Crie uma listagem de mídia, sincronização de insights ou publicação."
          action={
            <Link to="/publish" className="button button-primary">
              Ir para publicações
            </Link>
          }
        />
      ) : (
        <>
          <div className="table-wrap panel panel-flush">
            <table className="table">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Conta</th>
                  <th>Status</th>
                  <th>Tentativas</th>
                  <th>Criado</th>
                  <th>Duração</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const account = job.account_id
                    ? accountLabels.get(job.account_id) ?? undefined
                    : undefined;
                  return (
                    <JobRow
                      key={job.id}
                      job={job}
                      account={account}
                      expanded={expanded === job.id}
                      onToggle={() => setExpanded(expanded === job.id ? null : job.id)}
                      onCancel={() => void cancel(job)}
                      canceling={canceling === job.id}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>

          {hasMore && (
            <div className="load-more">
              <button
                type="button"
                className="button button-ghost"
                onClick={() => void load(false)}
                disabled={loadingMore}
              >
                {loadingMore ? "Carregando…" : "Carregar mais"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function JobRow({
  job,
  account,
  expanded,
  onToggle,
  onCancel,
  canceling,
}: {
  job: Job;
  account: Account | undefined;
  expanded: boolean;
  onToggle: () => void;
  onCancel: () => void;
  canceling: boolean;
}) {
  return (
    <>
      <tr className="job-row" onClick={onToggle}>
        <td>
          <strong>{jobTypeLabel(job.type)}</strong>
          <small className="job-id">{job.id.slice(0, 8)}</small>
        </td>
        <td>
          {account ? (
            <Link
              to={`/accounts/${account.id}`}
              className="text-link"
              onClick={(event) => event.stopPropagation()}
            >
              @{account.username}
            </Link>
          ) : (
            <span className="muted">—</span>
          )}
        </td>
        <td>
          <span className={`status status-${job.status}`}>
            {jobStatusLabel(job.status)}
          </span>
        </td>
        <td>
          {job.attempts}/{job.max_attempts}
        </td>
        <td className="muted">{formatShortDate(job.created_at)}</td>
        <td className="muted">{formatDuration(job.started_at, job.finished_at)}</td>
        <td onClick={(event) => event.stopPropagation()}>
          {job.status === "queued" && (
            <button
              type="button"
              className="button button-ghost button-small"
              onClick={onCancel}
              disabled={canceling}
            >
              <XCircle size={13} />
              Cancelar
            </button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="job-detail-row">
          <td colSpan={7}>
            <div className="job-detail">
              {job.error_code && (
                <div className="job-error">
                  <strong>{job.error_code}</strong>
                  <span>{job.error_message}</span>
                </div>
              )}
              <div className="job-meta">
                <span>ID {job.id}</span>
                <span>Prioridade {job.priority}</span>
                <span>Agendado {formatShortDate(job.run_after)}</span>
              </div>
              <div className="job-detail-grid">
                <div>
                  <span className="label">Payload</span>
                  <pre className="json-block">
                    {JSON.stringify(job.payload, null, 2)}
                  </pre>
                </div>
                <div>
                  <span className="label">Resultado</span>
                  <pre className="json-block">
                    {JSON.stringify(job.result ?? "Sem resultado ainda", null, 2)}
                  </pre>
                </div>
              </div>
              <JobAssets result={job.result} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
