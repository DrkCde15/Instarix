import { RefreshCw, ScrollText, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { EmptyState, JsonBlock, PageHeader, Spinner } from "../components/ui";
import { useToast } from "../toast";
import type { Account, AuditLog } from "../types";
import {
  auditActionLabel,
  formatDate,
  formatShortDate,
  jsonPreview,
} from "../utils";

export function AuditPage() {
  const { notify } = useToast();
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [action, setAction] = useState("");
  const [appliedAction, setAppliedAction] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

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
          api.audit({
            action: appliedAction || undefined,
            limit: 50,
            cursor: reset ? undefined : cursor ?? undefined,
          }),
          reset ? api.accounts(100) : Promise.resolve(null),
        ]);
        setLogs((current) => (reset ? page.items : [...current, ...page.items]));
        setCursor(page.next_cursor);
        setHasMore(Boolean(page.next_cursor));
        if (accountPage) setAccounts(accountPage.items);
      } catch (err) {
        notify(
          err instanceof ApiError ? err.message : "Falha ao carregar auditoria.",
          "error",
        );
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [appliedAction, cursor, notify],
  );

  useEffect(() => {
    void load(true);
  }, [appliedAction]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <Spinner label="Carregando auditoria" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Governança"
        title="Auditoria"
        description="Ações importantes da sua conta, sem senhas, códigos ou sessões."
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
        <div className="search-box">
          <Search size={16} />
          <input
            value={action}
            onChange={(event) => setAction(event.target.value)}
            placeholder="Filtrar por ação (ex.: account.created)"
            onKeyDown={(event) => {
              if (event.key === "Enter") setAppliedAction(action.trim());
            }}
          />
        </div>
        <div className="inline-actions">
          {appliedAction && (
            <button
              type="button"
              className="button button-ghost button-small"
              onClick={() => {
                setAction("");
                setAppliedAction("");
              }}
            >
              Limpar filtro
            </button>
          )}
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setAppliedAction(action.trim())}
          >
            Aplicar
          </button>
        </div>
      </div>

      {logs.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="Nenhum registro"
          description="Conecte uma conta ou crie uma integração para ver os registros aqui."
        />
      ) : (
        <>
          <div className="panel panel-flush table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Ação</th>
                  <th>Conta</th>
                  <th>Resumo</th>
                  <th>IP</th>
                  <th>Quando</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const account = log.account_id
                    ? accountLabels.get(log.account_id) ?? undefined
                    : undefined;
                  return (
                    <LogRow
                      key={log.id}
                      log={log}
                      account={account}
                      expanded={expanded === log.id}
                      onToggle={() =>
                        setExpanded(expanded === log.id ? null : log.id)
                      }
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

function LogRow({
  log,
  account,
  expanded,
  onToggle,
}: {
  log: AuditLog;
  account: Account | undefined;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="job-row" onClick={onToggle}>
        <td>
          <code className="action-code" title={log.action}>
            {auditActionLabel(log.action)}
          </code>
          <small className="job-id">{formatShortDate(log.created_at)}</small>
        </td>
        <td>{account ? `@${account.username}` : "—"}</td>
        <td className="muted">{jsonPreview(log.metadata)}</td>
        <td className="muted">{log.ip ?? "—"}</td>
        <td className="muted">{formatDate(log.created_at)}</td>
      </tr>
      {expanded && (
        <tr className="job-detail-row">
          <td colSpan={5}>
            <div className="job-detail">
              <div className="job-meta">
                <span>Log {log.id}</span>
                {log.user_id && <span>Usuário {log.user_id}</span>}
              </div>
              <span className="label">Metadados</span>
              <JsonBlock value={log.metadata} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
