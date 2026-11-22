import type { AccountStatus, JobStatus } from "./types";

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatShortDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value).getTime();
  if (Number.isNaN(date)) return "—";
  const diff = date - Date.now();
  const abs = Math.abs(diff);
  const formatter = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });
  if (abs < 60_000) return formatter.format(Math.round(diff / 1000), "second");
  if (abs < 3_600_000) return formatter.format(Math.round(diff / 60_000), "minute");
  if (abs < 86_400_000) return formatter.format(Math.round(diff / 3_600_000), "hour");
  return formatter.format(Math.round(diff / 86_400_000), "day");
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function accountStatusLabel(status: AccountStatus | string): string {
  return (
    {
      pending_login: "Aguardando login",
      active: "Ativa",
      "2fa_required": "2FA pendente",
      challenge_required: "Challenge",
      needs_reauth: "Reautenticar",
      disabled: "Desativada",
    }[status] ?? status
  );
}

export function jobStatusLabel(status: JobStatus | string): string {
  return (
    {
      queued: "Na fila",
      running: "Executando",
      awaiting_input: "Aguardando",
      succeeded: "Concluído",
      failed: "Falhou",
      canceled: "Cancelado",
    }[status] ?? status
  );
}

export function jobTypeLabel(type: string): string {
  return (
    {
      "media.list": "Listar mídia",
      "media.download": "Baixar mídia",
      "insights.account": "Insights",
      "account.health": "Health check",
      "publish.photo": "Publicar foto",
      "publish.video": "Publicar vídeo",
      "publish.reel": "Publicar reel",
      "publish.album": "Publicar álbum",
      "publish.story": "Publicar story",
    }[type] ?? type
  );
}

export function statusClass(value: string): string {
  return `status status-${value.replaceAll("_", "-")}`;
}

export function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (Number.isNaN(ms) || ms < 0) return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.round(ms / 60_000)} min`;
}

export function truncate(value: string, length = 90): string {
  if (value.length <= length) return value;
  return `${value.slice(0, length - 1)}…`;
}

export function isVideoContentType(contentType: string): boolean {
  return contentType.startsWith("video/");
}

export async function copyText(value: string): Promise<void> {
  await navigator.clipboard.writeText(value);
}

export function jsonPreview(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return truncate(value, 100);
  try {
    return truncate(JSON.stringify(value), 100);
  } catch {
    return "—";
  }
}
