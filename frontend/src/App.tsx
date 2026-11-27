import { Activity } from "lucide-react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { AccountDetailPage } from "./pages/AccountDetailPage";
import { AccountsPage } from "./pages/AccountsPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { AuditPage } from "./pages/AuditPage";
import { AutomationsPage } from "./pages/AutomationsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { FlowsPage } from "./pages/FlowsPage";
import { IntegrationsPage } from "./pages/IntegrationsPage";
import { JobsPage } from "./pages/JobsPage";
import { LoginPage } from "./pages/LoginPage";
import { PublishPage } from "./pages/PublishPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  const { me, loading } = useAuth();

  if (loading) {
    return (
      <div className="boot-screen">
        <div className="brand-mark brand-mark-large">
          <Activity size={26} />
        </div>
        <span>Instarix</span>
      </div>
    );
  }

  if (!me) return <LoginPage />;

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/flows" replace />} />
        <Route path="/flows" element={<FlowsPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/automations" element={<AutomationsPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route path="/accounts" element={<AccountsPage />} />
        <Route path="/accounts/:id" element={<AccountDetailPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/publish" element={<PublishPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/flows" replace />} />
      </Routes>
    </Layout>
  );
}
