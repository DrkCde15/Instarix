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
          <span className="eyebrow">Suas contas do Instagram, em um só lugar</span>
          <h1>
            Todas as suas contas.
            <br />
            <em>Um só controle.</em>
          </h1>
          <p>
            Conecte seus perfis, acompanhe publicações e veja o que precisa de
            atenção. Sem planilhas, sem sessões soltas.
          </p>
          <ul className="auth-features">
            <li>
              <ShieldCheck size={17} />
              Senhas e sessões protegidas
            </li>
            <li>
              <Radio size={17} />
              Publicações organizadas por conta
            </li>
            <li>
              <KeyRound size={17} />
              Integrações e histórico de ações
            </li>
          </ul>
        </div>
        <span className="auth-foot">Instarix</span>
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
                : "Crie sua conta e conecte o primeiro perfil do Instagram."}
            </p>
          </div>

          <form onSubmit={onSubmit} className="stack">
            {mode === "register" && (
              <label className="field">
                <span>Nome da empresa</span>
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
                  : "Criar conta"}
              {!submitting && <ArrowRight size={16} />}
            </button>
          </form>

          <p className="auth-note">
            O Instagram pode pedir uma verificação extra. O painel avisa quando
            isso acontece e nunca mostra suas senhas.
          </p>
        </div>
      </div>
    </div>
  );
}
