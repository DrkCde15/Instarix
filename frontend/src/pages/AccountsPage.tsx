import {
  ArrowUpRight,
  Clock,
  KeyRound,
  Plus,
  Search,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { EmptyState, Modal, PageHeader, Spinner } from "../components/ui";
import { useToast } from "../toast";
import type { Account } from "../types";
import { accountStatusLabel, formatShortDate, relativeTime } from "../utils";

export function AccountsPage() {
  const { notify } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(searchParams.get("new") === "1");
  const [label, setLabel] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [proxy, setProxy] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const page = await api.accounts(100);
      setAccounts(page.items);
    } catch (err) {
      notify(
        err instanceof ApiError ? err.message : "Falha ao carregar contas.",
        "error",
      );
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (searchParams.get("new") === "1") setModalOpen(true);
  }, [searchParams]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return accounts;
    return accounts.filter(
      (account) =>
        account.label.toLowerCase().includes(term) ||
        account.username.toLowerCase().includes(term),
    );
  }, [accounts, search]);

  function closeModal() {
    setModalOpen(false);
    if (searchParams.get("new")) {
      const next = new URLSearchParams(searchParams);
      next.delete("new");
      setSearchParams(next, { replace: true });
    }
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const account = await api.createAccount({
        label: label.trim(),
        username: username.trim().replace(/^@/, ""),
        password,
        ...(proxy.trim() ? { proxy: proxy.trim() } : {}),
      });
      notify(`Conta @${account.username} criada.`, "success");
      setLabel("");
      setUsername("");
      setPassword("");
      setProxy("");
      closeModal();
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Não foi possível criar a conta.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <Spinner label="Carregando contas" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Workspace"
        title="Contas do Instagram"
        description="Conecte, autentique e acompanhe o estado de cada conta."
        actions={
          <button
            type="button"
            className="button button-primary"
            onClick={() => setModalOpen(true)}
          >
            <Plus size={16} />
            Nova conta
          </button>
        }
      />

      <div className="toolbar">
        <div className="search-box">
          <Search size={16} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nome ou @username"
          />
          {search && (
            <button
              type="button"
              className="icon-button"
              onClick={() => setSearch("")}
            >
              <X size={14} />
            </button>
          )}
        </div>
        <span className="toolbar-count">
          {filtered.length} de {accounts.length} contas
        </span>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={Users}
          title={accounts.length ? "Nenhuma conta encontrada" : "Nenhuma conta conectada"}
          description={
            accounts.length
              ? "Tente outro termo de busca."
              : "Conecte a primeira conta para começar a usar o painel."
          }
          action={
            !accounts.length ? (
              <button
                type="button"
                className="button button-primary"
                onClick={() => setModalOpen(true)}
              >
                <Plus size={16} />
                Conectar conta
              </button>
            ) : undefined
          }
        />
      ) : (
        <div className="account-grid">
          {filtered.map((account) => (
            <Link
              key={account.id}
              to={`/accounts/${account.id}`}
              className={`account-card account-card-${account.status.replaceAll("_", "-")}`}
            >
              <div className="account-card-identity">
                <div className="avatar account-card-avatar">
                  {account.label.slice(0, 1).toUpperCase()}
                </div>
                <span
                  className={`status status-${account.status.replaceAll("_", "-")}`}
                >
                  {accountStatusLabel(account.status)}
                </span>
              </div>
              <div className="account-card-body">
                <div className="account-card-title">
                  <h3>{account.label}</h3>
                  <ArrowUpRight
                    size={16}
                    className="account-card-arrow"
                    aria-hidden="true"
                  />
                </div>
                <span className="handle">@{account.username}</span>
              </div>
              <div className="account-card-meta">
                <span className={account.has_session ? "meta-on" : "meta-off"}>
                  <ShieldCheck size={13} />
                  {account.has_session ? "Sessão salva" : "Sem sessão"}
                </span>
                <span className={account.has_proxy ? "meta-on" : "meta-off"}>
                  <KeyRound size={13} />
                  {account.has_proxy ? "Proxy ativo" : "Sem proxy"}
                </span>
              </div>
              <div className="account-card-foot">
                <span>
                  <Clock size={12} />
                  Login {formatShortDate(account.last_login_at)}
                </span>
                <span>criada {relativeTime(account.created_at)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      <Modal
        open={modalOpen}
        title="Conectar conta"
        description="Sua senha fica armazenada com criptografia e nunca é exibida no painel."
        onClose={closeModal}
      >
        <form className="stack" onSubmit={onCreate}>
          <label className="field">
            <span>Nome interno</span>
            <input
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Cliente A · Instagram"
              required
            />
          </label>
          <label className="field">
            <span>Username do Instagram</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="@minha_conta"
              required
            />
          </label>
          <label className="field">
            <span>Senha do Instagram</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              minLength={6}
              autoComplete="new-password"
              required
            />
          </label>
          <label className="field">
            <span>Proxy (opcional)</span>
            <input
              value={proxy}
              onChange={(event) => setProxy(event.target.value)}
              placeholder="http://usuario:senha@host:porta"
            />
          </label>
          {error && <div className="form-error">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="button button-ghost" onClick={closeModal}>
              Cancelar
            </button>
            <button type="submit" className="button button-primary" disabled={submitting}>
              {submitting ? "Conectando…" : "Criar conta"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
