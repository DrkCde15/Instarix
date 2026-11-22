import {
  ChevronDown,
  ChevronUp,
  Plus,
  Radio,
  Trash2,
  Webhook,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import {
  CopyButton,
  EmptyState,
  JsonBlock,
  Modal,
  PageHeader,
  Spinner,
} from "../components/ui";
import { useToast } from "../toast";
import type { WebhookDelivery, WebhookEndpoint } from "../types";
import { formatDate, formatShortDate } from "../utils";

const EVENTS = [
  { value: "job.succeeded", label: "Job concluído" },
  { value: "job.failed", label: "Job falhou" },
];

export function WebhooksPage() {
  const { notify } = useToast();
  const [endpoints, setEndpoints] = useState<WebhookEndpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>(["job.succeeded", "job.failed"]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<Record<string, WebhookDelivery[]>>({});
  const [loadingDeliveries, setLoadingDeliveries] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEndpoints(await api.webhooks());
    } catch (err) {
      notify(
        err instanceof ApiError ? err.message : "Falha ao carregar webhooks.",
        "error",
      );
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!events.length) {
      setError("Selecione ao menos um evento.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await api.createWebhook({ url: url.trim(), events });
      setNewSecret(created.secret);
      setModalOpen(false);
      setUrl("");
      notify("Webhook criado. Guarde o segredo exibido.", "success");
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Não foi possível criar o webhook.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(endpoint: WebhookEndpoint) {
    if (!window.confirm(`Remover o webhook ${endpoint.url}?`)) return;
    try {
      await api.deleteWebhook(endpoint.id);
      notify("Webhook removido.", "success");
      if (expanded === endpoint.id) setExpanded(null);
      await load();
    } catch (err) {
      notify(err instanceof ApiError ? err.message : "Falha ao remover.", "error");
    }
  }

  async function toggleDeliveries(endpointId: string) {
    if (expanded === endpointId) {
      setExpanded(null);
      return;
    }
    setExpanded(endpointId);
    if (deliveries[endpointId]) return;
    setLoadingDeliveries(endpointId);
    try {
      const rows = await api.deliveries(endpointId);
      setDeliveries((current) => ({ ...current, [endpointId]: rows }));
    } catch (err) {
      notify(
        err instanceof ApiError ? err.message : "Falha ao carregar entregas.",
        "error",
      );
    } finally {
      setLoadingDeliveries(null);
    }
  }

  function toggleEvent(value: string) {
    setEvents((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  }

  if (loading) return <Spinner label="Carregando webhooks" />;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Integrações"
        title="Webhooks"
        description="Receba eventos dos jobs com assinatura HMAC e retry automático."
        actions={
          <button
            type="button"
            className="button button-primary"
            onClick={() => setModalOpen(true)}
          >
            <Plus size={16} />
            Novo webhook
          </button>
        }
      />

      {newSecret && (
        <div className="secret-banner">
          <div>
            <strong>Segredo do webhook — exibido uma única vez</strong>
            <p>
              Use este valor para validar a assinatura HMAC-SHA256. Ele não pode
              ser recuperado depois.
            </p>
            <code>{newSecret}</code>
          </div>
          <div className="secret-actions">
            <CopyButton value={newSecret} label="Copiar segredo" />
            <button
              type="button"
              className="icon-button"
              onClick={() => setNewSecret(null)}
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      {endpoints.length === 0 ? (
        <EmptyState
          icon={Webhook}
          title="Nenhum webhook configurado"
          description="Cadastre um endpoint para receber job.succeeded e job.failed."
          action={
            <button
              type="button"
              className="button button-primary"
              onClick={() => setModalOpen(true)}
            >
              <Plus size={16} />
              Criar webhook
            </button>
          }
        />
      ) : (
        <div className="webhook-list">
          {endpoints.map((endpoint) => (
            <article key={endpoint.id} className="panel webhook-card">
              <div className="webhook-main">
                <div className="webhook-icon">
                  <Radio size={18} />
                </div>
                <div className="webhook-info">
                  <div className="webhook-url">
                    <code>{endpoint.url}</code>
                    <span
                      className={`status ${endpoint.is_active ? "status-active" : "status-disabled"}`}
                    >
                      {endpoint.is_active ? "ativo" : "inativo"}
                    </span>
                  </div>
                  <div className="event-chips">
                    {endpoint.events.map((event) => (
                      <span key={event}>{event}</span>
                    ))}
                    <small>criado {formatDate(endpoint.created_at)}</small>
                  </div>
                </div>
                <div className="webhook-actions">
                  <button
                    type="button"
                    className="button button-ghost button-small"
                    onClick={() => void toggleDeliveries(endpoint.id)}
                  >
                    Entregas
                    {expanded === endpoint.id ? (
                      <ChevronUp size={14} />
                    ) : (
                      <ChevronDown size={14} />
                    )}
                  </button>
                  <button
                    type="button"
                    className="icon-button icon-danger"
                    onClick={() => void remove(endpoint)}
                    aria-label="Remover webhook"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>

              {expanded === endpoint.id && (
                <div className="deliveries">
                  {loadingDeliveries === endpoint.id ? (
                    <Spinner label="Carregando entregas" />
                  ) : (deliveries[endpoint.id] ?? []).length === 0 ? (
                    <p className="muted">Nenhuma entrega registrada ainda.</p>
                  ) : (
                    <div className="table-wrap">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Evento</th>
                            <th>Status</th>
                            <th>Tentativas</th>
                            <th>HTTP</th>
                            <th>Quando</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(deliveries[endpoint.id] ?? []).map((delivery) => (
                            <tr key={delivery.id}>
                              <td>
                                <code>{delivery.event}</code>
                              </td>
                              <td>
                                <span className={`status status-${delivery.status}`}>
                                  {delivery.status}
                                </span>
                              </td>
                              <td>
                                {delivery.attempts}/{delivery.max_attempts}
                              </td>
                              <td>{delivery.response_status ?? "—"}</td>
                              <td className="muted">
                                {formatShortDate(delivery.created_at)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {(deliveries[endpoint.id] ?? []).some(
                    (delivery) => delivery.error_code,
                  ) && (
                    <details className="json-details">
                      <summary>Ver último payload/erro</summary>
                      {(() => {
                        const failed = (deliveries[endpoint.id] ?? []).find(
                          (delivery) => delivery.error_code,
                        );
                        if (!failed) return null;
                        return (
                          <>
                            <p className="muted">
                              {failed.error_code}: {failed.error_message}
                            </p>
                            <JsonBlock value={failed.payload} />
                          </>
                        );
                      })()}
                    </details>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      <Modal
        open={modalOpen}
        title="Novo webhook"
        description="O endpoint precisa responder 2xx para confirmar a entrega."
        onClose={() => setModalOpen(false)}
      >
        <form className="stack" onSubmit={onCreate}>
          <label className="field">
            <span>URL HTTPS</span>
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://seu-servico.com/webhooks/instarix"
              required
            />
          </label>
          <div className="field">
            <span>Eventos</span>
            <div className="checkbox-grid">
              {EVENTS.map((event) => (
                <label key={event.value} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={events.includes(event.value)}
                    onChange={() => toggleEvent(event.value)}
                  />
                  <span>
                    <strong>{event.label}</strong>
                    <code>{event.value}</code>
                  </span>
                </label>
              ))}
            </div>
          </div>
          {error && <div className="form-error">{error}</div>}
          <div className="modal-actions">
            <button
              type="button"
              className="button button-ghost"
              onClick={() => setModalOpen(false)}
            >
              Cancelar
            </button>
            <button type="submit" className="button button-primary" disabled={submitting}>
              {submitting ? "Criando…" : "Criar webhook"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
