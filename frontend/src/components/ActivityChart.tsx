import { formatShortDate } from "../utils";

export function ActivityChart({
  data,
}: {
  data: Array<{ date: string; runs: number }>;
}) {
  const max = Math.max(1, ...data.map((point) => point.runs));

  return (
    <div className="activity-chart" role="img" aria-label="Execuções por dia">
      {data.map((point) => (
        <div key={point.date} className="chart-column">
          <div
            className="chart-bar"
            style={{ height: `${Math.max(3, (point.runs / max) * 100)}%` }}
            title={`${formatShortDate(point.date)}: ${point.runs} execução(ões)`}
          />
          <small>{point.date.slice(5)}</small>
        </div>
      ))}
    </div>
  );
}
