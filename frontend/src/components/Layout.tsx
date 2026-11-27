import {
  Activity,
  BarChart3,
  ChevronRight,
  GitBranch,
  LayoutDashboard,
  ListTodo,
  LogOut,
  Megaphone,
  Menu,
  MessageCircle,
  PanelLeftClose,
  PanelLeftOpen,
  PlugZap,
  ScrollText,
  Send,
  Settings,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import { roleLabel } from "../utils";

type NavItem = {
  label: string;
  icon: typeof Activity;
  to?: string;
};

const navGroups: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "Principal",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { to: "/automations", label: "Automações", icon: Workflow },
      { to: "/flows", label: "Construtor de Fluxos", icon: GitBranch },
    ],
  },
  {
    label: "Operação",
    items: [
      { to: "/accounts", label: "Contas", icon: Users },
      { to: "/jobs", label: "Fila de tarefas", icon: ListTodo },
      { to: "/publish", label: "Publicar", icon: Send },
      { label: "Conversas", icon: MessageCircle },
      { label: "Contatos", icon: Users },
      { label: "Campanhas", icon: Megaphone },
      { to: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    label: "Sistema",
    items: [
      { to: "/integrations", label: "Integrações", icon: PlugZap },
      { to: "/audit", label: "Auditoria", icon: ScrollText },
      { to: "/settings", label: "Configurações", icon: Settings },
    ],
  },
];

const titles: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/automations": "Automações",
  "/flows": "Construtor de Fluxos",
  "/analytics": "Analytics",
  "/integrations": "Integrações",
  "/accounts": "Contas",
  "/jobs": "Fila de tarefas",
  "/publish": "Publicar",
  "/audit": "Auditoria",
  "/settings": "Configurações",
};

export function Layout({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("instarix:sidebar-collapsed") === "1",
  );
  const title =
    titles[location.pathname] ??
    (location.pathname.startsWith("/accounts/") ? "Conta" : "Instarix");

  useEffect(() => {
    localStorage.setItem(
      "instarix:sidebar-collapsed",
      collapsed ? "1" : "0",
    );
  }, [collapsed]);

  return (
    <div className={`app-shell ${collapsed ? "shell-collapsed" : ""}`}>
      {open && (
        <button
          type="button"
          className="sidebar-backdrop"
          onClick={() => setOpen(false)}
          aria-label="Fechar menu"
        />
      )}
      <aside
        className={`sidebar ${open ? "sidebar-open" : ""} ${collapsed ? "sidebar-collapsed" : ""}`}
      >
        <div className="brand">
          <div className="brand-mark">
            <Activity size={21} />
          </div>
          <div className="brand-copy">
            <strong>Instarix</strong>
            <span>automações</span>
          </div>
          <button
            type="button"
            className="icon-button sidebar-collapse"
            onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
            title={collapsed ? "Expandir menu" : "Recolher menu"}
          >
            {collapsed ? (
              <PanelLeftOpen size={17} />
            ) : (
              <PanelLeftClose size={17} />
            )}
          </button>
          <button
            type="button"
            className="icon-button sidebar-close"
            onClick={() => setOpen(false)}
            aria-label="Fechar menu"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="nav">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-section">{group.label}</span>
              {group.items.map((item) =>
                item.to ? (
                  <NavLink
                    key={item.label}
                    to={item.to}
                    className={({ isActive }) =>
                      isActive ? "nav-link active" : "nav-link"
                    }
                    onClick={() => setOpen(false)}
                    title={collapsed ? item.label : undefined}
                  >
                    <item.icon size={17} />
                    <span>{item.label}</span>
                    <ChevronRight size={14} className="nav-chevron" />
                  </NavLink>
                ) : (
                  <span
                    key={item.label}
                    className="nav-link nav-soon"
                    title="Disponível em breve"
                  >
                    <item.icon size={17} />
                    <span>{item.label}</span>
                    <small>em breve</small>
                  </span>
                ),
              )}
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
            <span className="tenant-role">{roleLabel(me?.role)}</span>
          </div>
          <button
            type="button"
            className="button button-ghost logout"
            onClick={logout}
          >
            <LogOut size={15} />
            <span>Sair</span>
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
            {roleLabel(me?.role)}
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
