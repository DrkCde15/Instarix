import {
  ArrowUpRight,
  ListTodo,
  Plus,
  RefreshCw,
  Send,
  ShieldAlert,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { EmptyState, PageHeader, Spinner, StatCard } from "../components/ui";
import type { Account, Job, Usage } from "../types";
import {
  accountStatusLabel,
  formatShortDate,
  jobStatusLabel,
  jobTypeLabel,
  relativeTime,
} from "../utils";
import { useToast } from "../toast";

export function DashboardPage() {
  const { notify } = useToast();
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
        const [nextUsage, accountPage, jobPage] = await Promise.all([
          api.usage(),
          api.accounts(100),
          api.jobs({ limit: 6 }),
        ]);
        setUsage(nextUsage);
        setAccounts(accountPage.items);
        setJobs(jobPage.items);
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "Falha ao carregar a visão geral.";
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

  if (loading) return <Spinner label="Carregando visão geral" />;

  const active = accounts.filter((account) => account.status === "active").length;
  const attention = accounts.filter((account) =>
    ["2fa_required", "needs_reauth", "challenge_required"].includes(account.status),
  );
  const recent = [...accounts]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 5);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Operação"
        title="Visão geral"
        description="O pulso das suas contas, fila e consumo em um só lugar."
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
            <Link className="button button-primary" to="/accounts?new=1">
              <Plus size={16} />
              Nova conta
            </Link>
          </>
        }
      />

      {error && <div className="error-banner">{error}</div>}

      <section className="stats-grid">
        <StatCard
          label="Contas conectadas"
          value={`${usage?.accounts_used ?? accounts.length}`}
          hint={
            usage?.accounts_limit
              ? `de ${usage.accounts_limit} no plano ${usage.plan}`
              : `plano ${usage?.plan ?? "—"} · ilimitado`
          }
          icon={Users}
          accent="teal"
        />
        <StatCard
          label="Contas ativas"
          value={active}
          hint={`${accounts.length - active} em outro estado`}
          icon={ShieldAlert}
          accent="violet"
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
        <StatCard
          label="Precisam de atenção"
          value={attention.length}
          hint={
            attention.length
              ? attention
                  .slice(0, 2)
                  .map((account) => `@${account.username}`)
                  .join(", ")
              : "tudo em ordem"
          }
          icon={ShieldAlert}
          accent={attention.length ? "red" : "teal"}
        />
      </section>

      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Contas recentes</h2>
              <p>Estados de sessão e últimos acessos.</p>
            </div>
            <Link to="/accounts" className="text-link">
              Ver todas <ArrowUpRight size={14} />
            </Link>
          </div>
          {recent.length === 0 ? (
            <EmptyState
              icon={Users}
              title="Nenhuma conta ainda"
              description="Conecte a primeira conta para começar a operar pelo painel."
              action={
                <Link className="button button-primary" to="/accounts?new=1">
                  <Plus size={16} />
                  Conectar conta
                </Link>
              }
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Conta</th>
                    <th>Estado</th>
                    <th>Último login</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((account) => (
                    <tr key={account.id}>
                      <td>
                        <Link to={`/accounts/${account.id}`} className="row-title">
                          <span className="avatar avatar-small">
                            {account.label.slice(0, 1).toUpperCase()}
                          </span>
                          <span>
                            <strong>{account.label}</strong>
                            <small>@{account.username}</small>
                          </span>
                        </Link>
                      </td>
                      <td>
                        <span className={`status status-${account.status.replaceAll("_", "-")}`}>
                          {accountStatusLabel(account.status)}
                        </span>
                      </td>
                      <td className="muted">{formatShortDate(account.last_login_at)}</td>
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
              <h2>Fila recente</h2>
              <p>Últimos jobs criados no workspace.</p>
            </div>
            <Link to="/jobs" className="text-link">
              Ver fila <ArrowUpRight size={14} />
            </Link>
          </div>
          {jobs.length === 0 ? (
            <EmptyState
              icon={ListTodo}
              title="Fila vazia"
              description="Enfileire uma listagem de mídia ou publicação para ver os jobs aqui."
              action={
                <Link className="button button-ghost" to="/publish">
                  <Send size={15} />
                  Publicar algo
                </Link>
              }
            />
          ) : (
            <ul className="activity-list">
              {jobs.map((job) => (
                <li key={job.id} className="activity-item">
                  <div className={`activity-dot activity-${job.status}`} />
                  <div className="activity-body">
                    <div className="activity-title">
                      <strong>{jobTypeLabel(job.type)}</strong>
                      <span className={`status status-${job.status}`}>
                        {jobStatusLabel(job.status)}
                      </span>
                    </div>
                    <small>
                      {relativeTime(job.created_at)} · tentativa {job.attempts}/
                      {job.max_attempts}
                    </small>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {attention.length > 0 && (
        <section className="panel attention-panel">
          <div className="panel-header">
            <div>
              <h2>Contas que precisam de você</h2>
              <p>2FA, reautenticação ou challenge exigem ação no app oficial.</p>
            </div>
          </div>
          <div className="attention-list">
            {attention.map((account) => (
              <Link
                key={account.id}
                to={`/accounts/${account.id}`}
                className="attention-item"
              >
                <div>
                  <strong>@{account.username}</strong>
                  <span>{accountStatusLabel(account.status)}</span>
                </div>
                <ArrowUpRight size={16} />
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
