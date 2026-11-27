import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { ActivityChart } from "../components/ActivityChart";
import { PageHeader, Spinner, StatCard } from "../components/ui";
import type { FlowSummary } from "../types";
import { jobStatusLabel, relativeTime } from "../utils";
import { useToast } from "../toast";

export function AnalyticsPage() {
  const { notify } = useToast();
  const [summary, setSummary] = useState<FlowSummary | null>(null);

  useEffect(() => {
    let active = true;
    api
      .flowsSummary()
      .then((data) => {
        if (active) setSummary(data);
      })
      .catch((err) =>
        notify(
          err instanceof ApiError ? err.message : "Falha ao carregar analytics.",
          "error",
        ),
      );
    return () => {
      active = false;
    };
  }, [notify]);

  if (!summary) return <Spinner label="Carregando analytics" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Métricas"
        title="Analytics"
        description="Indicadores reais das execuções das suas automações."
      />

      <section className="stats-grid">
        <StatCard label="Execuções" value={summary.total_runs} hint="registradas" />
        <StatCard
          label="Concluídas"
          value={summary.succeeded_runs}
          hint="execuções com sucesso"
        />
        <StatCard
          label="Taxa de sucesso"
          value={`${summary.success_rate.toFixed(1)}%`}
          hint="sobre o total"
        />
        <StatCard
          label="Fluxos ativos"
          value={summary.active_flows}
          hint={`de ${summary.total_flows} automações`}
        />
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Execuções por dia</h2>
            <p>Últimos 14 dias.</p>
          </div>
        </div>
        <ActivityChart data={summary.activity} />
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Histórico de execuções</h2>
            <p>As corridas mais recentes do workspace.</p>
          </div>
        </div>
        {summary.recent_runs.length === 0 ? (
          <p className="muted">Nenhuma execução registrada.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Gatilho</th>
                  <th>Status</th>
                  <th>Etapas</th>
                  <th>Quando</th>
                </tr>
              </thead>
              <tbody>
                {summary.recent_runs.map((run) => (
                  <tr key={run.id}>
                    <td>{run.trigger}</td>
                    <td>
                      <span className={`status status-${run.status}`}>
                        {jobStatusLabel(run.status)}
                      </span>
                    </td>
                    <td>{run.steps.length}</td>
                    <td className="muted">{relativeTime(run.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
