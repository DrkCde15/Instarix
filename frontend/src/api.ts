import type {
  Account,
  AccountPage,
  ApiKey,
  ApiKeyCreated,
  AuditLogPage,
  InsightsSnapshot,
  Job,
  JobPage,
  LoginAttempt,
  Me,
  MediaCache,
  TokenPair,
  UploadResult,
  Usage,
  WebhookDelivery,
  WebhookEndpoint,
  WebhookEndpointCreated,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(
  /\/$/,
  "",
) ?? "";

const ACCESS_KEY = "instarix.access";
const REFRESH_KEY = "instarix.refresh";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export const tokens = {
  access: () => localStorage.getItem(ACCESS_KEY),
  refresh: () => localStorage.getItem(REFRESH_KEY),
  set(pair: TokenPair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

function expireSession() {
  tokens.clear();
  window.dispatchEvent(new CustomEvent("instarix:auth-expired"));
}

async function parseError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `A API respondeu ${response.status}.`;
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string };
      detail?: unknown;
    };
    if (body.error?.code) code = body.error.code;
    if (body.error?.message) {
      message = body.error.message;
    } else if (typeof body.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      // Erros de validação do FastAPI vêm como uma lista de {loc, msg}.
      const first = body.detail[0] as
        | { msg?: string; loc?: Array<string | number> }
        | undefined;
      if (first?.msg) {
        const field = first.loc?.filter((part) => part !== "body").join(".");
        message = field ? `${field}: ${first.msg}` : first.msg;
        code = "validation_error";
      }
    }
  } catch {
    // resposta sem JSON; mantém a mensagem padrão
  }
  return new ApiError(response.status, code, message);
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const refresh = tokens.refresh();
  if (!refresh) return false;
  if (!refreshPromise) {
    refreshPromise = fetch(`${BASE}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    })
      .then(async (response) => {
        if (!response.ok) return false;
        const pair = (await response.json()) as TokenPair;
        tokens.set(pair);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
  skipRefresh?: boolean;
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { skipAuth, skipRefresh, headers, ...init } = options;
  const finalHeaders = new Headers(headers);
  const access = tokens.access();
  if (!skipAuth && access) {
    finalHeaders.set("Authorization", `Bearer ${access}`);
  }
  if (init.body && !(init.body instanceof FormData)) {
    finalHeaders.set("Content-Type", "application/json");
  }

  let response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: finalHeaders,
  });

  if (response.status === 401 && !skipAuth && !skipRefresh) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      const retryHeaders = new Headers(headers);
      const nextAccess = tokens.access();
      if (nextAccess) retryHeaders.set("Authorization", `Bearer ${nextAccess}`);
      if (init.body && !(init.body instanceof FormData)) {
        retryHeaders.set("Content-Type", "application/json");
      }
      response = await fetch(`${BASE}${path}`, {
        ...init,
        headers: retryHeaders,
      });
    } else {
      expireSession();
    }
  }

  if (!response.ok) {
    if (response.status === 401) expireSession();
    throw await parseError(response);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  async login(email: string, password: string): Promise<TokenPair> {
    const pair = await request<TokenPair>("/v1/auth/token", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      skipAuth: true,
      skipRefresh: true,
    });
    tokens.set(pair);
    return pair;
  },

  async register(input: {
    tenant_name: string;
    email: string;
    password: string;
  }): Promise<TokenPair> {
    const pair = await request<TokenPair>("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(input),
      skipAuth: true,
      skipRefresh: true,
    });
    tokens.set(pair);
    return pair;
  },

  async logout(): Promise<void> {
    const refresh = tokens.refresh();
    if (refresh) {
      try {
        await request<void>("/v1/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: refresh }),
          skipAuth: true,
          skipRefresh: true,
        });
      } catch {
        // logout local continua mesmo se o remoto falhar
      }
    }
    tokens.clear();
  },

  me: () => request<Me>("/v1/me"),

  accounts(limit = 100, cursor?: string) {
    return request<AccountPage>(
      `/v1/accounts${query({ limit, cursor })}`,
    );
  },

  account: (id: string) => request<Account>(`/v1/accounts/${id}`),

  createAccount(input: {
    label: string;
    username: string;
    password: string;
    proxy?: string;
  }) {
    return request<Account>("/v1/accounts", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  updateAccount(
    id: string,
    input: { label?: string; password?: string; proxy?: string | null },
  ) {
    return request<Account>(`/v1/accounts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },

  deleteAccount: (id: string) =>
    request<void>(`/v1/accounts/${id}`, { method: "DELETE" }),

  loginAccount: (id: string) =>
    request<Account>(`/v1/accounts/${id}/login`, { method: "POST" }),

  submit2fa: (id: string, code: string) =>
    request<Account>(`/v1/accounts/${id}/2fa`, {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  logoutAccount: (id: string) =>
    request<void>(`/v1/accounts/${id}/logout`, { method: "POST" }),

  health: (id: string) => request<Account>(`/v1/accounts/${id}/health`),

  loginAttempts: (id: string) =>
    request<LoginAttempt[]>(`/v1/accounts/${id}/login-attempts?limit=50`),

  jobs(params: {
    account_id?: string;
    status?: string;
    type?: string;
    limit?: number;
    cursor?: string;
  } = {}) {
    return request<JobPage>(`/v1/jobs${query(params)}`);
  },

  job: (id: string) => request<Job>(`/v1/jobs/${id}`),

  createJob(
    accountId: string,
    input: {
      type: string;
      payload?: Record<string, unknown>;
      priority?: number;
      idempotency_key?: string;
    },
  ) {
    return request<Job>(`/v1/accounts/${accountId}/jobs`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  cancelJob: (id: string) =>
    request<Job>(`/v1/jobs/${id}/cancel`, { method: "POST" }),

  media: (accountId: string) =>
    request<MediaCache>(`/v1/accounts/${accountId}/media`),

  insights: (accountId: string) =>
    request<InsightsSnapshot>(`/v1/accounts/${accountId}/insights`),

  syncInsights: (accountId: string) =>
    request<Job>(`/v1/accounts/${accountId}/insights/sync`, { method: "POST" }),

  usage: () => request<Usage>("/v1/usage"),

  upload(file: File): Promise<UploadResult> {
    const body = new FormData();
    body.append("file", file);
    return request<UploadResult>("/v1/uploads", { method: "POST", body });
  },

  webhooks: () => request<WebhookEndpoint[]>("/v1/webhooks"),

  createWebhook(input: { url: string; events: string[] }) {
    return request<WebhookEndpointCreated>("/v1/webhooks", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  deleteWebhook: (id: string) =>
    request<void>(`/v1/webhooks/${id}`, { method: "DELETE" }),

  deliveries: (id: string) =>
    request<WebhookDelivery[]>(`/v1/webhooks/${id}/deliveries?limit=100`),

  audit(params: {
    action?: string;
    account_id?: string;
    limit?: number;
    cursor?: string;
  } = {}) {
    return request<AuditLogPage>(`/v1/audit-logs${query(params)}`);
  },

  apiKeys: () => request<ApiKey[]>("/v1/api-keys"),

  createApiKey(input: { name: string; scopes: string[] }) {
    return request<ApiKeyCreated>("/v1/api-keys", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  revokeApiKey: (id: string) =>
    request<void>(`/v1/api-keys/${id}`, { method: "DELETE" }),

  async downloadAsset(assetId: string, filename: string): Promise<void> {
    const authHeaders = () => {
      const headers = new Headers();
      const access = tokens.access();
      if (access) headers.set("Authorization", `Bearer ${access}`);
      return headers;
    };

    let response = await fetch(`${BASE}/v1/media/${assetId}`, {
      headers: authHeaders(),
    });
    if (response.status === 401 && (await refreshTokens())) {
      response = await fetch(`${BASE}/v1/media/${assetId}`, {
        headers: authHeaders(),
      });
    }
    if (!response.ok) {
      if (response.status === 401) expireSession();
      throw await parseError(response);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  },

  async metricsText(): Promise<string> {
    const headers = new Headers();
    const access = tokens.access();
    if (access) headers.set("Authorization", `Bearer ${access}`);
    const response = await fetch(`${BASE}/v1/metrics`, { headers });
    if (!response.ok) throw await parseError(response);
    return response.text();
  },
};
