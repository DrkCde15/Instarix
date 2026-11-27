import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  Download,
  History,
  Image as ImageIcon,
  ListTodo,
  LogIn,
  LogOut,
  Pencil,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { JobAssets } from "../components/JobAssets";
import {
  EmptyState,
  ErrorBanner,
  JsonBlock,
  Modal,
  Spinner,
} from "../components/ui";
import { useToast } from "../toast";
import type {
  Account,
  InsightsSnapshot,
  Job,
  LoginAttempt,
  MediaCache,
  MediaItem,
} from "../types";
import {
  accountErrorLabel,
  accountStatusLabel,
  formatDate,
  formatDuration,
  formatShortDate,
  jobStatusLabel,
  jobTypeLabel,
  loginAttemptStatusLabel,
  relativeTime,
} from "../utils";

type Tab = "media" | "insights" | "jobs" | "history";

function mediaKinds(item: MediaItem): ("photo" | "video")[] {
  if (item.media_type === 2) return ["video"];
  if (item.media_type === 1) return ["photo"];
  if (item.media_type === 8) return ["photo", "video"];
  return ["photo"];
}

export function AccountDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { notify } = useToast();
  const [account, setAccount] = useState<Account | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [attempts, setAttempts] = useState<LoginAttempt[]>([]);
  const [media, setMedia] = useState<MediaCache | null>(null);
  const [insights, setInsights] = useState<InsightsSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("media");
  const [action, setAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mediaError, setMediaError] = useState<string | null>(null);
  const [insightsError, setInsightsError] = useState<string | null>(null);
  const [mediaAmount, setMediaAmount] = useState(12);
  const [twoFactorCode, setTwoFactorCode] = useState("");
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editLabel, setEditLabel] = useState("");
  const [editPassword, setEditPassword] = useState("");
  const [editProxy, setEditProxy] = useState("");
  const [replaceProxy, setReplaceProxy] = useState(false);

  const loadMedia = useCallback(async () => {
    if (!id) return;
    try {
      setMedia(await api.media(id));
      setMediaError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setMedia(null);
        setMediaError(null);
        return;
      }
      setMediaError(
        err instanceof ApiError ? err.message : "Falha ao carregar a mídia salva.",
      );
    }
  }, [id]);

  const loadInsights = useCallback(async () => {
    if (!id) return;
    try {
      setInsights(await api.insights(id));
      setInsightsError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setInsights(null);
        setInsightsError(null);
        return;
      }
      setInsightsError(
        err instanceof ApiError ? err.message : "Falha ao ler insights.",
      );
    }
  }, [id]);

  const load = useCallback(
    async (silent = false) => {
      if (!id) return;
      if (!silent) setLoading(true);
      try {
        const [nextAccount, jobPage, nextAttempts] = await Promise.all([
          api.account(id),
          api.jobs({ account_id: id, limit: 50 }),
          api.loginAttempts(id),
        ]);
        setAccount(nextAccount);
        setJobs(jobPage.items);
        setAttempts(nextAttempts);
        setError(null);
        await Promise.all([loadMedia(), loadInsights()]);
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "Falha ao carregar a conta.";
        setError(message);
        if (silent) notify(message, "error");
      } finally {
        setLoading(false);
      }
    },
    [id, loadInsights, loadMedia, notify],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const activeJobs = jobs.some(
    (job) => job.status === "queued" || job.status === "running",
  );
  useEffect(() => {
    if (!activeJobs) return;
    const timer = window.setInterval(() => void load(true), 4000);
    return () => window.clearInterval(timer);
  }, [activeJobs, load]);

  useEffect(() => {
    if (account) {
      setEditLabel(account.label);
      setEditProxy("");
      setReplaceProxy(false);
    }
  }, [account]);

  async function runAction(
    name: string,
    actionFn: () => Promise<unknown>,
    successMessage: string,
  ) {
    setAction(name);
    setError(null);
    try {
      await actionFn();
      notify(successMessage, "success");
      await load(true);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Não foi possível concluir a ação.",
      );
    } finally {
      setAction(null);
    }
  }

  async function submitTwoFactor(event: FormEvent) {
    event.preventDefault();
    if (!id || !twoFactorCode.trim()) return;
    await runAction(
      "2fa",
      () => api.submit2fa(id, twoFactorCode.trim()),
      "Código confirmado.",
    );
    setTwoFactorCode("");
  }

  async function enqueueMediaList() {
    if (!id) return;
    await runAction(
      "media.list",
      () =>
        api.createJob(id, {
          type: "media.list",
          payload: { amount: mediaAmount },
        }),
      "Busca de mídia iniciada. Acompanhe o andamento abaixo.",
    );
  }

  async function downloadMedia(item: MediaItem, kind: "photo" | "video") {
    if (!id) return;
    await runAction(
      `download-${item.pk}-${kind}`,
      () =>
        api.createJob(id, {
          type: "media.download",
          payload: { media_pk: item.pk, kinds: [kind] },
        }),
      "Download iniciado.",
    );
  }

  async function syncInsights() {
    if (!id) return;
    await runAction(
      "insights",
      () => api.syncInsights(id),
      "Insights serão atualizados em instantes.",
    );
  }

  async function cancelJob(jobId: string) {
    await runAction(
      `cancel-${jobId}`,
      () => api.cancelJob(jobId),
      "Tarefa cancelada.",
    );
  }

  async function saveAccount(event: FormEvent) {
    event.preventDefault();
    if (!id) return;
    const payload: { label?: string; password?: string; proxy?: string | null } = {};
    if (editLabel.trim() && editLabel.trim() !== account?.label) {
      payload.label = editLabel.trim();
    }
    if (editPassword) payload.password = editPassword;
    if (replaceProxy) payload.proxy = editProxy.trim() || null;
    if (!Object.keys(payload).length) {
      setEditOpen(false);
      return;
    }
    await runAction(
      "update",
      () => api.updateAccount(id, payload),
      "Conta atualizada.",
    );
    setEditPassword("");
    setEditOpen(false);
  }

  async function deleteAccount() {
    if (!id) return;
    if (
      !window.confirm(
        "Excluir esta conta? A sessão será removida e o perfil liberado para outra conexão.",
      )
    ) {
      return;
    }
    setAction("delete");
    try {
      await api.deleteAccount(id);
      notify("Conta excluída.", "success");
      navigate("/accounts");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao excluir conta.");
    } finally {
      setAction(null);
    }
  }

  if (loading) return <Spinner label="Carregando conta" />;
  if (!account) {
    return (
      <div className="page">
        <ErrorBanner message={error ?? "Conta não encontrada."} />
        <Link to="/accounts" className="button button-ghost">
          <ArrowLeft size={15} />
          Voltar para contas
        </Link>
      </div>
    );
  }

  const scalarInsights = insights
    ? Object.entries(insights.data).filter(
        ([, value]) => typeof value === "number" || typeof value === "string",
      )
    : [];

  return (
    <div className="page">
      <Link to="/accounts" className="back-link">
        <ArrowLeft size={15} />
        Contas
      </Link>

      <header className="account-hero">
        <div className="account-identity">
          <div className="avatar avatar-xl">
            {account.label.slice(0, 1).toUpperCase()}
          </div>
          <div>
            <div className="account-title-line">
              <h1>{account.label}</h1>
              <span
                className={`status status-${account.status.replaceAll("_", "-")}`}
              >
                {accountStatusLabel(account.status)}
              </span>
            </div>
            <p>
              @{account.username} · criada {relativeTime(account.created_at)}
            </p>
            <div className="meta-chips">
              <span>{account.has_session ? "Sessão salva" : "Sem sessão"}</span>
              <span>{account.has_proxy ? "Proxy ativo" : "Sem proxy"}</span>
              <span>Último login {formatShortDate(account.last_login_at)}</span>
            </div>
          </div>
        </div>
        <div className="account-actions">
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setEditOpen(true)}
          >
            <Pencil size={15} />
            Editar
          </button>
          <button
            type="button"
            className="button button-ghost"
            onClick={() =>
              void runAction(
                "login",
                () => api.loginAccount(account.id),
                "Login concluído.",
              )
            }
            disabled={action !== null || account.status === "disabled"}
          >
            <LogIn size={15} />
            {account.status === "needs_reauth" ? "Reautenticar" : "Login"}
          </button>
          <button
            type="button"
            className="button button-ghost"
            onClick={() =>
              void runAction(
                "health",
                () => api.health(account.id),
                "Sessão verificada.",
              )
            }
            disabled={action !== null || !account.has_session}
          >
            <ShieldCheck size={15} />
            Validar sessão
          </button>
          <button
            type="button"
            className="button button-ghost"
            onClick={() =>
              void runAction(
                "logout",
                () => api.logoutAccount(account.id),
                "Sessão descartada.",
              )
            }
            disabled={action !== null || !account.has_session}
          >
            <LogOut size={15} />
            Logout
          </button>
        </div>
      </header>

      <ErrorBanner message={error} />

      {account.last_error_code && (
        <div className="warning-banner">
          <AlertTriangle size={17} />
          <div>
            <strong>{accountErrorLabel(account.last_error_code)}</strong>
            <span>
              {account.status === "challenge_required"
                ? "Resolva a verificação no app oficial e tente o login novamente."
                : account.status === "needs_reauth"
                  ? "A sessão foi recusada. Reautentique ou atualize a senha."
                  : "Última falha registrada pela conta."}
            </span>
          </div>
        </div>
      )}

      {account.status === "2fa_required" && (
        <form className="twofa-panel" onSubmit={submitTwoFactor}>
          <div className="twofa-copy">
            <strong>Código de verificação pendente</strong>
            <p>
              Informe o código enviado pelo Instagram. Ele não é armazenado.
            </p>
          </div>
          <div className="twofa-input">
            <input
              value={twoFactorCode}
              onChange={(event) => setTwoFactorCode(event.target.value)}
              placeholder="123456"
              minLength={4}
              maxLength={16}
              aria-label="Código de verificação"
              required
            />
            <button
              type="submit"
              className="button button-primary"
              disabled={action !== null}
            >
              {action === "2fa" ? "Validando…" : "Confirmar"}
            </button>
          </div>
        </form>
      )}

      <div className="tabs">
        <button
          type="button"
          className={tab === "media" ? "tab active" : "tab"}
          onClick={() => setTab("media")}
        >
          <ImageIcon size={15} />
          Mídia
        </button>
        <button
          type="button"
          className={tab === "insights" ? "tab active" : "tab"}
          onClick={() => setTab("insights")}
        >
          <BarChart3 size={15} />
          Insights
        </button>
        <button
          type="button"
          className={tab === "jobs" ? "tab active" : "tab"}
          onClick={() => setTab("jobs")}
        >
          <ListTodo size={15} />
          Tarefas
          {jobs.length > 0 && <span className="tab-count">{jobs.length}</span>}
        </button>
        <button
          type="button"
          className={tab === "history" ? "tab active" : "tab"}
          onClick={() => setTab("history")}
        >
          <History size={15} />
          Histórico
        </button>
      </div>

      {tab === "media" && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Mídia recente</h2>
              <p>
                {media
                  ? `${media.items.length} posts salvos · atualizado ${formatShortDate(media.cached_at)}`
                  : "Nenhuma mídia salva ainda."}
              </p>
            </div>
            <div className="inline-actions">
              <label className="mini-field">
                Quantidade
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={mediaAmount}
                  onChange={(event) => setMediaAmount(Number(event.target.value))}
                />
              </label>
              <button
                type="button"
                className="button button-primary"
                onClick={() => void enqueueMediaList()}
                disabled={action !== null}
              >
                <RefreshCw
                  size={15}
                  className={action === "media.list" ? "spin" : ""}
                />
                Buscar mídia
              </button>
            </div>
          </div>

          {mediaError && <div className="error-banner">{mediaError}</div>}

          {!media ? (
            <EmptyState
              icon={ImageIcon}
              title="Nenhuma mídia salva"
              description="Busque os posts recentes desta conta para vê-los aqui."
              action={
                <button
                  type="button"
                  className="button button-primary"
                  onClick={() => void enqueueMediaList()}
                  disabled={action !== null}
                >
                  Buscar mídia agora
                </button>
              }
            />
          ) : media.items.length === 0 ? (
            <EmptyState
              icon={ImageIcon}
              title="Nenhum post encontrado"
              description="A conta pode não ter posts públicos ou o Instagram limitou a leitura."
            />
          ) : (
            <div className="media-grid">
              {media.items.map((item) => {
                const kinds = mediaKinds(item);
                return (
                  <article key={item.pk} className="media-card">
                    <div className="media-thumb">
                      {item.thumbnail_url ? (
                        <img src={item.thumbnail_url} alt="" loading="lazy" />
                      ) : (
                        <ImageIcon size={26} />
                      )}
                      <span className="media-type">
                        {item.media_type === 2
                          ? "vídeo"
                          : item.media_type === 8
                            ? "álbum"
                            : "foto"}
                      </span>
                    </div>
                    <div className="media-body">
                      <p>{item.caption?.trim() || "Sem legenda"}</p>
                      <small>
                        {item.like_count ?? 0} curtidas ·{" "}
                        {item.comment_count ?? 0} comentários
                      </small>
                      <code>{item.pk}</code>
                    </div>
                    <div className="media-actions">
                      {kinds.includes("photo") && (
                        <button
                          type="button"
                          className="button button-ghost button-small"
                          onClick={() => void downloadMedia(item, "photo")}
                          disabled={action !== null}
                        >
                          <Download size={13} />
                          Foto
                        </button>
                      )}
                      {kinds.includes("video") && (
                        <button
                          type="button"
                          className="button button-ghost button-small"
                          onClick={() => void downloadMedia(item, "video")}
                          disabled={action !== null}
                        >
                          <Download size={13} />
                          Vídeo
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}

      {tab === "insights" && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Insights da conta</h2>
              <p>
                {insights
                  ? `Dados capturados em ${formatDate(insights.captured_at)}`
                  : "Ainda não há dados salvos."}
              </p>
            </div>
            <button
              type="button"
              className="button button-primary"
              onClick={() => void syncInsights()}
              disabled={action !== null}
            >
              <RefreshCw
                size={15}
                className={action === "insights" ? "spin" : ""}
              />
              Sincronizar
            </button>
          </div>
          {insightsError && <div className="error-banner">{insightsError}</div>}
          {!insights ? (
            <EmptyState
              icon={BarChart3}
              title="Sem insights ainda"
              description="Sincronize para ver os dados mais recentes."
              action={
                <button
                  type="button"
                  className="button button-primary"
                  onClick={() => void syncInsights()}
                  disabled={action !== null}
                >
                  Sincronizar insights
                </button>
              }
            />
          ) : (
            <>
              {scalarInsights.length > 0 && (
                <div className="metric-grid">
                  {scalarInsights.map(([key, value]) => (
                    <div key={key} className="metric-card">
                      <span>{key.replaceAll("_", " ")}</span>
                      <strong>{String(value)}</strong>
                    </div>
                  ))}
                </div>
              )}
              <details className="json-details">
                <summary>Ver dados completos</summary>
                <JsonBlock value={insights.data} />
              </details>
            </>
          )}
        </section>
      )}

      {tab === "jobs" && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Tarefas desta conta</h2>
              <p>Uma tarefa por vez por conta, para evitar conflitos.</p>
            </div>
            <button
              type="button"
              className="button button-ghost"
              onClick={() => void load(true)}
            >
              <RefreshCw size={15} />
              Atualizar
            </button>
          </div>
          {jobs.length === 0 ? (
            <EmptyState
              icon={ListTodo}
              title="Nenhuma tarefa"
              description="Buscas de mídia, insights e publicações aparecem aqui."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Status</th>
                    <th>Tentativas</th>
                    <th>Criado</th>
                    <th>Duração</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <JobRow
                      key={job.id}
                      job={job}
                      expanded={expandedJob === job.id}
                      onToggle={() =>
                        setExpandedJob(expandedJob === job.id ? null : job.id)
                      }
                      onCancel={() => void cancelJob(job.id)}
                      canceling={action === `cancel-${job.id}`}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {tab === "history" && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Histórico de login</h2>
              <p>Senhas e códigos de verificação nunca aparecem aqui.</p>
            </div>
          </div>
          {attempts.length === 0 ? (
            <EmptyState
              icon={History}
              title="Sem tentativas"
              description="O histórico aparece após o primeiro login."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Método</th>
                    <th>Tentativas</th>
                    <th>Erro</th>
                    <th>Criado</th>
                    <th>Concluído</th>
                  </tr>
                </thead>
                <tbody>
                  {attempts.map((attempt) => (
                    <tr key={attempt.id}>
                      <td>
                        <span className={`status status-${attempt.status.replaceAll("_", "-")}`}>
                          {loginAttemptStatusLabel(attempt.status)}
                        </span>
                      </td>
                      <td>{attempt.method ?? "—"}</td>
                      <td>{attempt.attempts}</td>
                      <td className="muted">{attempt.error_code ?? "—"}</td>
                      <td className="muted">{formatShortDate(attempt.created_at)}</td>
                      <td className="muted">{formatShortDate(attempt.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <Modal
        open={editOpen}
        title="Editar conta"
        description="Ao trocar a senha, você precisará entrar novamente na conta."
        onClose={() => setEditOpen(false)}
      >
        <form className="stack" onSubmit={saveAccount}>
          <label className="field">
            <span>Nome interno</span>
            <input
              value={editLabel}
              onChange={(event) => setEditLabel(event.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>Nova senha do Instagram</span>
            <input
              type="password"
              value={editPassword}
              onChange={(event) => setEditPassword(event.target.value)}
              placeholder="Deixe em branco para manter"
              minLength={6}
              autoComplete="new-password"
            />
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={replaceProxy}
              onChange={(event) => setReplaceProxy(event.target.checked)}
            />
            Substituir/remover proxy
          </label>
          {replaceProxy && (
            <label className="field">
              <span>Proxy</span>
              <input
                value={editProxy}
                onChange={(event) => setEditProxy(event.target.value)}
                placeholder="Vazio remove o proxy"
              />
            </label>
          )}
          <div className="modal-actions modal-actions-split">
            <button
              type="button"
              className="button button-danger"
              onClick={() => void deleteAccount()}
              disabled={action !== null}
            >
              <Trash2 size={15} />
              Excluir conta
            </button>
            <div className="inline-actions">
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setEditOpen(false)}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="button button-primary"
                disabled={action !== null}
              >
                {action === "update" ? "Salvando…" : "Salvar"}
              </button>
            </div>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function JobRow({
  job,
  expanded,
  onToggle,
  onCancel,
  canceling,
}: {
  job: Job;
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
              Cancelar
            </button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="job-detail-row">
          <td colSpan={6}>
            <div className="job-detail">
              {job.error_code && (
                <div className="job-error">
                  <strong>Falha na tarefa</strong>
                  <span title={job.error_code}>{job.error_message}</span>
                </div>
              )}
              <div className="job-detail-grid">
                <div>
                  <span className="label">Payload</span>
                  <JsonBlock value={job.payload} />
                </div>
                <div>
                  <span className="label">Resultado</span>
                  <JsonBlock value={job.result ?? "Sem resultado ainda"} />
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
