import { Activity, ArrowUpRight, ListTodo, Plus, RefreshCw, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { ActivityChart } from "../components/ActivityChart";
import { EmptyState, PageHeader, Spinner, StatCard } from "../components/ui";
import type { Account, FlowSummary, Job, Usage } from "../types";
import { jobStatusLabel, jobTypeLabel, relativeTime } from "../utils";
import { useToast } from "../toast";

export function DashboardPage() {
  const { notify } = useToast();
  const [summary, setSummary] = useState<FlowSummary | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      setRefreshing(true);
      setError(null);
      try {
        const [nextSummary, nextUsage, accountPage, jobPage] = await Promise.all([
          api.flowsSummary(),
          api.usage(),
          api.accounts(100),
          api.jobs({ limit: 6 }),
        ]);
        setSummary(nextSummary);
        setUsage(nextUsage);
        setAccounts(accountPage.items);
        setJobs(jobPage.items);
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "Falha ao carregar o dashboard.";
        setError(message);
        if (silent) notify(message, "error");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [notify],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <Spinner label="Carregando dashboard" />;

  const successRate = summary?.success_rate ?? 0;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Visão geral"
        title="Dashboard"
        description="O desempenho das suas automações e o estado da operação."
        actions={
          <>
            <button
              type="button"
              className="button button-ghost"
              onClick={() => void load(true)}
              disabled={refreshing}
            >
              <RefreshCw size={15} className={refreshing ? "spin" : ""} />
              Atualizar
            </button>
            <Link className="button button-primary" to="/flows">
              <Plus size={16} />
              Novo fluxo
            </Link>
          </>
        }
      />

      {error && <div className="error-banner">{error}</div>}

      <section className="stats-grid">
        <StatCard
          label="Automações"
          value={summary?.total_flows ?? 0}
          hint={`${summary?.draft_flows ?? 0} rascunho(s)`}
          icon={Activity}
          accent="teal"
        />
        <StatCard
          label="Ativas"
          value={summary?.active_flows ?? 0}
          hint={`${summary?.paused_flows ?? 0} pausada(s)`}
          icon={Activity}
          accent="violet"
        />
        <StatCard
          label="Execuções"
          value={summary?.total_runs ?? 0}
          hint={`${summary?.succeeded_runs ?? 0} concluídas`}
          icon={ListTodo}
          accent="amber"
        />
        <StatCard
          label="Taxa de sucesso"
          value={`${successRate.toFixed(1)}%`}
          hint="sobre as execuções registradas"
          icon={Activity}
          accent={successRate >= 80 ? "teal" : "red"}
        />
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Atividade das automações</h2>
            <p>Execuções nos últimos 14 dias.</p>
          </div>
          <Link to="/analytics" className="text-link">
            Ver analytics <ArrowUpRight size={14} />
          </Link>
        </div>
        <ActivityChart data={summary?.activity ?? []} />
      </section>

      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Automações mais usadas</h2>
              <p>Ordenadas por número de execuções.</p>
            </div>
            <Link to="/automations" className="text-link">
              Gerenciar <ArrowUpRight size={14} />
            </Link>
          </div>
          {!summary?.top_flows.length ? (
            <EmptyState
              icon={Activity}
              title="Nenhuma execução ainda"
              description="Crie um fluxo e execute um teste para ver dados aqui."
              action={
                <Link className="button button-primary" to="/flows">
                  Criar fluxo
                </Link>
              }
            />
          ) : (
            <ol className="ranked-list">
              {summary.top_flows.map((flow, index) => (
                <li key={flow.flow_id}>
                  <span className="rank-number">{index + 1}</span>
                  <Link to={`/flows?id=${flow.flow_id}`} className="row-title">
                    {flow.name}
                  </Link>
                  <span className="muted">{flow.runs} execuções</span>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Execuções recentes</h2>
              <p>Últimas corridas registradas.</p>
            </div>
          </div>
          {!summary?.recent_runs.length ? (
            <p className="muted">Nenhuma execução registrada.</p>
          ) : (
            <ul className="activity-list">
              {summary.recent_runs.map((run) => (
                <li key={run.id} className="activity-item">
                  <div className={`activity-dot activity-${run.status}`} />
                  <div className="activity-body">
                    <div className="activity-title">
                      <strong>{run.trigger}</strong>
                      <span className={`status status-${run.status}`}>
                        {jobStatusLabel(run.status)}
                      </span>
                    </div>
                    <small>{relativeTime(run.created_at)}</small>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Operação</h2>
            <p>Contas conectadas e fila de jobs do workspace.</p>
          </div>
          <Link to="/jobs" className="text-link">
            Ver fila <ArrowUpRight size={14} />
          </Link>
        </div>
        <div className="stats-grid stats-grid-compact">
          <StatCard
            label="Contas conectadas"
            value={`${usage?.accounts_used ?? accounts.length}`}
            hint={
              usage?.accounts_limit
                ? `de ${usage.accounts_limit} no plano ${usage.plan}`
                : `plano ${usage?.plan ?? "—"}`
            }
            icon={Users}
            accent="teal"
          />
          <StatCard
            label="Jobs hoje"
            value={usage?.jobs_today_used ?? 0}
            hint={
              usage?.jobs_today_limit
                ? `de ${usage.jobs_today_limit}`
                : "sem limite diário"
            }
            icon={ListTodo}
            accent="amber"
          />
        </div>
        {jobs.length > 0 && (
          <ul className="compact-list">
            {jobs.slice(0, 4).map((job) => (
              <li key={job.id}>
                <span>{jobTypeLabel(job.type)}</span>
                <span className={`status status-${job.status}`}>
                  {jobStatusLabel(job.status)}
                </span>
                <small>{relativeTime(job.created_at)}</small>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
