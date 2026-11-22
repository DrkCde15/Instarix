import {
  Activity,
  ChevronRight,
  LayoutDashboard,
  ListTodo,
  LogOut,
  Menu,
  ScrollText,
  Send,
  Settings,
  Users,
  Webhook,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../auth";

const navGroups = [
  {
    label: "Operação",
    items: [
      { to: "/", label: "Visão geral", icon: LayoutDashboard },
      { to: "/accounts", label: "Contas", icon: Users },
      { to: "/jobs", label: "Jobs", icon: ListTodo },
      { to: "/publish", label: "Publicar", icon: Send },
    ],
  },
  {
    label: "Gestão",
    items: [
      { to: "/webhooks", label: "Webhooks", icon: Webhook },
      { to: "/audit", label: "Auditoria", icon: ScrollText },
      { to: "/settings", label: "Configurações", icon: Settings },
    ],
  },
];

const titles: Record<string, string> = {
  "/": "Visão geral",
  "/accounts": "Contas",
  "/jobs": "Jobs",
  "/publish": "Publicar",
  "/webhooks": "Webhooks",
  "/audit": "Auditoria",
  "/settings": "Configurações",
};

export function Layout({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const title =
    titles[location.pathname] ??
    (location.pathname.startsWith("/accounts/") ? "Conta" : "Instarix");

  return (
    <div className="app-shell">
      {open && (
        <button
          type="button"
          className="sidebar-backdrop"
          onClick={() => setOpen(false)}
          aria-label="Fechar menu"
        />
      )}
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <Activity size={21} />
          </div>
          <div>
            <strong>Instarix</strong>
            <span>control center</span>
          </div>
          <button
            type="button"
            className="icon-button sidebar-close"
            onClick={() => setOpen(false)}
          >
            <X size={18} />
          </button>
        </div>

        <nav className="nav">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-section">{group.label}</span>
              {group.items.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    isActive ? "nav-link active" : "nav-link"
                  }
                  onClick={() => setOpen(false)}
                >
                  <Icon size={17} />
                  <span>{label}</span>
                  <ChevronRight size={14} className="nav-chevron" />
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="tenant-chip">
            <div className="avatar">{me?.email.slice(0, 1).toUpperCase()}</div>
            <div className="tenant-meta">
              <strong>{me?.tenant_slug}</strong>
              <span>{me?.email}</span>
            </div>
            <span className="tenant-role">{me?.role}</span>
          </div>
          <button type="button" className="button button-ghost logout" onClick={logout}>
            <LogOut size={15} />
            Sair
          </button>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <button
            type="button"
            className="icon-button menu-button"
            onClick={() => setOpen(true)}
            aria-label="Abrir menu"
          >
            <Menu size={20} />
          </button>
          <div className="topbar-title">{title}</div>
          <div className="topbar-role">
            <span className="dot" />
            {me?.role}
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
