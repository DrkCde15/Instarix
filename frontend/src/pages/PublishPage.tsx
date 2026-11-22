import {
  AlertTriangle,
  CheckCircle2,
  FileImage,
  Send,
  UploadCloud,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { EmptyState, PageHeader, Spinner } from "../components/ui";
import { useToast } from "../toast";
import type { Account, Job } from "../types";
import {
  formatBytes,
  isVideoContentType,
  jobStatusLabel,
  jobTypeLabel,
} from "../utils";

const TYPES = [
  { value: "publish.photo", label: "Foto no feed", multiple: false },
  { value: "publish.video", label: "Vídeo no feed", multiple: false },
  { value: "publish.reel", label: "Reel", multiple: false },
  { value: "publish.album", label: "Álbum / carrossel", multiple: true },
  { value: "publish.story", label: "Story", multiple: false },
] as const;

type PublishType = (typeof TYPES)[number]["value"];

export function PublishPage() {
  const { notify } = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [accountId, setAccountId] = useState("");
  const [type, setType] = useState<PublishType>("publish.photo");
  const [files, setFiles] = useState<File[]>([]);
  const [thumbnail, setThumbnail] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);

  const selectedType = useMemo(
    () => TYPES.find((item) => item.value === type) ?? TYPES[0],
    [type],
  );
  const needsThumbnail = type === "publish.video" || type === "publish.reel";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const page = await api.accounts(100);
      setAccounts(page.items);
      const firstActive =
        page.items.find((account) => account.status === "active") ?? page.items[0];
      if (firstActive) setAccountId(firstActive.id);
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
    if (!job || ["succeeded", "failed", "canceled"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        setJob(await api.job(job.id));
      } catch {
        // mantém o último estado conhecido
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [job]);

  function onFiles(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files ?? []);
    setFiles(selectedType.multiple ? selected.slice(0, 10) : selected.slice(0, 1));
    setError(null);
  }

  function validate(): string | null {
    if (!accountId) return "Escolha uma conta.";
    if (files.length === 0) return "Selecione ao menos um arquivo.";
    if (type === "publish.album" && (files.length < 2 || files.length > 10)) {
      return "Um álbum precisa de 2 a 10 arquivos.";
    }
    if (type !== "publish.album" && files.length > 1) {
      return "Esse tipo aceita apenas um arquivo.";
    }
    if (type === "publish.story" && files.length === 0) {
      return "Selecione a mídia do story.";
    }
    return null;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const validation = validate();
    if (validation) {
      setError(validation);
      return;
    }
    setError(null);
    setSubmitting(true);
    setJob(null);
    try {
      const uploads = [];
      for (const file of files) {
        uploads.push(await api.upload(file));
      }
      let thumbnailKey: string | undefined;
      if (needsThumbnail && thumbnail) {
        thumbnailKey = (await api.upload(thumbnail)).storage_key;
      }

      let payload: Record<string, unknown>;
      if (type === "publish.album") {
        payload = {
          storage_keys: uploads.map((upload) => upload.storage_key),
          caption,
        };
      } else if (type === "publish.story") {
        payload = {
          storage_key: uploads[0].storage_key,
          kind: isVideoContentType(uploads[0].content_type) ? "video" : "photo",
          caption,
        };
      } else {
        payload = {
          storage_key: uploads[0].storage_key,
          caption,
          ...(thumbnailKey ? { thumbnail_key: thumbnailKey } : {}),
        };
      }

      const created = await api.createJob(accountId, {
        type,
        payload,
        idempotency_key: crypto.randomUUID(),
      });
      setJob(created);
      setFiles([]);
      setThumbnail(null);
      notify("Publicação enfileirada.", "success");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível enviar a publicação.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <Spinner label="Carregando contas" />;

  if (accounts.length === 0) {
    return (
      <div className="page">
        <PageHeader
          eyebrow="Conteúdo"
          title="Publicar"
          description="Envie mídia e enfileire a publicação em uma conta."
        />
        <EmptyState
          icon={Send}
          title="Nenhuma conta para publicar"
          description="Conecte e autentique uma conta antes de criar uma publicação."
          action={
            <Link to="/accounts?new=1" className="button button-primary">
              Conectar conta
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Conteúdo"
        title="Publicar"
        description="O upload é local; o job usa a sessão da conta e protege contra post duplicado."
      />

      <div className="publish-layout">
        <form className="panel stack" onSubmit={onSubmit}>
          <div className="panel-header">
            <div>
              <h2>Nova publicação</h2>
              <p>Escolha a conta, o formato e os arquivos.</p>
            </div>
          </div>

          <label className="field">
            <span>Conta</span>
            <select
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
              required
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.label} (@{account.username}) · {account.status}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Formato</span>
            <select
              value={type}
              onChange={(event) => {
                setType(event.target.value as PublishType);
                setFiles([]);
                setThumbnail(null);
              }}
            >
              {TYPES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <div className="field">
            <span>Arquivos</span>
            <label className="dropzone">
              <UploadCloud size={24} />
              <strong>
                {files.length
                  ? `${files.length} arquivo(s) selecionado(s)`
                  : "Clique para escolher imagem ou vídeo"}
              </strong>
              <small>
                JPEG, PNG, WebP, MP4 ou MOV · até 25 MiB por arquivo
              </small>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime"
                multiple={selectedType.multiple}
                onChange={onFiles}
                hidden
              />
            </label>
            {files.length > 0 && (
              <ul className="file-list">
                {files.map((file) => (
                  <li key={`${file.name}-${file.size}`}>
                    <FileImage size={15} />
                    <span>{file.name}</span>
                    <small>{formatBytes(file.size)}</small>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() =>
                        setFiles((current) =>
                          current.filter((item) => item !== file),
                        )
                      }
                    >
                      <X size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {needsThumbnail && (
            <label className="field">
              <span>Capa do vídeo (opcional)</span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(event) =>
                  setThumbnail(event.target.files?.[0] ?? null)
                }
              />
              {thumbnail && <small>{thumbnail.name}</small>}
            </label>
          )}

          <label className="field">
            <span>Legenda</span>
            <textarea
              value={caption}
              onChange={(event) => setCaption(event.target.value)}
              placeholder="Escreva a legenda da publicação…"
              maxLength={2200}
              rows={4}
            />
            <small>{caption.length}/2200</small>
          </label>

          {error && <div className="form-error">{error}</div>}

          <button
            type="submit"
            className="button button-primary button-block"
            disabled={submitting}
          >
            {submitting ? (
              <>
                <UploadCloud size={16} className="bounce" />
                Enviando e enfileirando…
              </>
            ) : (
              <>
                <Send size={16} />
                Enfileirar publicação
              </>
            )}
          </button>

          <div className="info-note">
            <AlertTriangle size={16} />
            <span>
              Se o Instagram não confirmar a publicação, o job fica com{" "}
              <code>ambiguous_publish</code> e não repete sozinho. Confira o
              perfil antes de tentar novamente.
            </span>
          </div>
        </form>

        <aside className="publish-side">
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2>Como funciona</h2>
                <p>O fluxo é assíncrono de ponta a ponta.</p>
              </div>
            </div>
            <ol className="steps">
              <li>
                <strong>Upload</strong>
                <p>O arquivo vai para o storage local compartilhado.</p>
              </li>
              <li>
                <strong>Fila</strong>
                <p>O job é serializado por conta e executado pelo worker.</p>
              </li>
              <li>
                <strong>Confirmação</strong>
                <p>O resultado fica no job, com proteção contra duplicidade.</p>
              </li>
            </ol>
          </div>

          {job && (
            <div className="panel job-result-card">
              <div className="panel-header">
                <div>
                  <h2>Job criado</h2>
                  <p>{jobTypeLabel(job.type)}</p>
                </div>
                {job.status === "succeeded" ? (
                  <CheckCircle2 className="success-icon" size={20} />
                ) : (
                  <span className={`status status-${job.status}`}>
                    {jobStatusLabel(job.status)}
                  </span>
                )}
              </div>
              <code className="job-id-full">{job.id}</code>
              {job.error_code && (
                <div className="job-error">
                  <strong>{job.error_code}</strong>
                  <span>{job.error_message}</span>
                </div>
              )}
              {job.result && (
                <pre className="json-block">
                  {JSON.stringify(job.result, null, 2)}
                </pre>
              )}
              <Link to="/jobs" className="button button-ghost button-block">
                Acompanhar na fila
              </Link>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
