import { KeyRound, Settings, Webhook } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { PageHeader, Spinner } from "../components/ui";
import type { ApiKey } from "../types";
import { formatShortDate } from "../utils";
import { useToast } from "../toast";

export function IntegrationsPage() {
  const { notify } = useToast();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);

  useEffect(() => {
    let active = true;
    api
      .apiKeys()
      .then((data) => {
        if (active) setKeys(data);
      })
      .catch((err) =>
        notify(
          err instanceof ApiError ? err.message : "Falha ao carregar integrações.",
          "error",
        ),
      );
    return () => {
      active = false;
    };
  }, [notify]);

  if (!keys) return <Spinner label="Carregando integrações" />;

  const activeKeys = keys.filter((key) => !key.revoked_at).length;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Conexões"
        title="Integrações"
        description="Recursos disponíveis para conectar o Instarix a outros sistemas."
      />

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Chaves de API</h2>
            <p>
              {activeKeys} ativa(s) · use no cabeçalho X-API-Key para chamar a API v1.
            </p>
          </div>
          <Link to="/settings" className="button button-ghost">
            <Settings size={15} />
            Gerenciar
          </Link>
        </div>
        {keys.length === 0 ? (
          <p className="muted">
            Nenhuma chave criada. Crie uma em Configurações para integrar serviços.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Prefixo</th>
                  <th>Escopos</th>
                  <th>Último uso</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.id}>
                    <td>
                      <strong>{key.name}</strong>
                      {key.revoked_at && (
                        <span className="status status-canceled">revogada</span>
                      )}
                    </td>
                    <td>
                      <code>{key.key_prefix}…</code>
                    </td>
                    <td className="muted">{key.scopes.length} escopo(s)</td>
                    <td className="muted">{formatShortDate(key.last_used_at)}</td>
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
            <h2>Entrega de eventos</h2>
            <p>Webhooks de saída são configurados pela API.</p>
          </div>
          <Webhook size={18} />
        </div>
        <div className="feature-note">
          <KeyRound size={16} />
          <p>
            Os eventos <code>job.succeeded</code> e <code>job.failed</code> são
            entregues com assinatura HMAC-SHA256. Cadastre endpoints com{" "}
            <code>POST /v1/webhooks</code> usando uma chave com escopo
            <code> webhooks:write</code>.
          </p>
        </div>
      </section>
    </div>
  );
}
