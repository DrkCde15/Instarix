import { ArrowRight, Activity, KeyRound, Radio, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ApiError } from "../api";
import { useAuth } from "../auth";

export function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [tenantName, setTenantName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "register") {
        await register({
          tenant_name: tenantName.trim(),
          email: email.trim(),
          password,
        });
      } else {
        await login(email.trim(), password);
      }
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível concluir a autenticação.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-visual">
        <div className="auth-glow auth-glow-one" />
        <div className="auth-glow auth-glow-two" />
        <div className="auth-brand">
          <div className="brand-mark brand-mark-large">
            <Activity size={26} />
          </div>
          <span>Instarix</span>
        </div>
        <div className="auth-copy">
          <span className="eyebrow">Instagram operations, organized</span>
          <h1>
            Todas as suas contas.
            <br />
            <em>Um só controle.</em>
          </h1>
          <p>
            Login com 2FA, leitura de mídia, publicação e insights em uma fila
            serializada por conta. Sem planilhas, sem sessões soltas.
          </p>
          <ul className="auth-features">
            <li>
              <ShieldCheck size={17} />
              Credenciais e sessões cifradas
            </li>
            <li>
              <Radio size={17} />
              Fila por conta com retry e recuperação
            </li>
            <li>
              <KeyRound size={17} />
              API keys, webhooks e audit log
            </li>
          </ul>
        </div>
        <span className="auth-foot">Instarix API · v0.1</span>
      </div>

      <div className="auth-panel">
        <div className="auth-card">
          <div className="auth-tabs">
            <button
              type="button"
              className={mode === "login" ? "active" : ""}
              onClick={() => {
                setMode("login");
                setError(null);
              }}
            >
              Entrar
            </button>
            <button
              type="button"
              className={mode === "register" ? "active" : ""}
              onClick={() => {
                setMode("register");
                setError(null);
              }}
            >
              Criar conta
            </button>
          </div>

          <div className="auth-heading">
            <h2>{mode === "login" ? "Bem-vindo de volta" : "Comece agora"}</h2>
            <p>
              {mode === "login"
                ? "Use seu email e senha para acessar o painel."
                : "Crie seu workspace e conecte a primeira conta do Instagram."}
            </p>
          </div>

          <form onSubmit={onSubmit} className="stack">
            {mode === "register" && (
              <label className="field">
                <span>Nome do workspace</span>
                <input
                  value={tenantName}
                  onChange={(event) => setTenantName(event.target.value)}
                  placeholder="Minha agência"
                  minLength={2}
                  required
                />
              </label>
            )}
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="voce@empresa.com"
                autoComplete="email"
                required
              />
            </label>
            <label className="field">
              <span>Senha</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "register" ? 8 : 1}
                required
              />
              {mode === "register" && (
                <small>Mínimo de 8 caracteres.</small>
              )}
            </label>

            {error && <div className="form-error">{error}</div>}

            <button
              type="submit"
              className="button button-primary button-block"
              disabled={submitting}
            >
              {submitting
                ? "Conectando…"
                : mode === "login"
                  ? "Entrar no painel"
                  : "Criar workspace"}
              {!submitting && <ArrowRight size={16} />}
            </button>
          </form>

          <p className="auth-note">
            A API privada do Instagram pode exigir verificação manual. O painel
            mostra o estado de cada conta e nunca expõe senhas ou sessões.
          </p>
        </div>
      </div>
    </div>
  );
}
