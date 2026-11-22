export type AccountStatus =
  | "pending_login"
  | "active"
  | "2fa_required"
  | "challenge_required"
  | "needs_reauth"
  | "disabled";

export type JobStatus =
  | "queued"
  | "running"
  | "awaiting_input"
  | "succeeded"
  | "failed"
  | "canceled";

export interface Me {
  user_id: string;
  tenant_id: string;
  tenant_slug: string;
  email: string;
  role: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Account {
  id: string;
  label: string;
  username: string;
  status: AccountStatus;
  has_proxy: boolean;
  has_session: boolean;
  last_login_at: string | null;
  last_error_code: string | null;
  created_at: string;
}

export interface AccountPage {
  items: Account[];
  next_cursor: string | null;
}

export interface LoginAttempt {
  id: string;
  status: string;
  method: string | null;
  attempts: number;
  error_code: string | null;
  created_at: string;
  expires_at: string | null;
  finished_at: string | null;
}

export interface Job {
  id: string;
  account_id: string | null;
  type: string;
  payload: Record<string, unknown>;
  status: JobStatus;
  priority: number;
  run_after: string;
  attempts: number;
  max_attempts: number;
  result: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  idempotency_key: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface JobPage {
  items: Job[];
  next_cursor: string | null;
}

export interface MediaItem {
  pk: string;
  id?: string;
  code?: string | null;
  media_type?: number | null;
  product_type?: string | null;
  taken_at?: string | null;
  caption?: string | null;
  thumbnail_url?: string | null;
  video_url?: string | null;
  like_count?: number | null;
  comment_count?: number | null;
  username?: string | null;
}

export interface MediaCache {
  job_id: string;
  username: string;
  items: MediaItem[];
  cached_at: string | null;
}

export interface InsightsSnapshot {
  id: string;
  account_id: string;
  data: Record<string, unknown>;
  captured_at: string;
}

export interface Usage {
  plan: string;
  accounts_used: number;
  accounts_limit: number;
  jobs_today_used: number;
  jobs_today_limit: number;
}

export interface UploadResult {
  storage_key: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface WebhookEndpoint {
  id: string;
  url: string;
  events: string[];
  is_active: boolean;
  created_at: string;
}

export interface WebhookEndpointCreated extends WebhookEndpoint {
  secret: string;
}

export interface WebhookDelivery {
  id: string;
  endpoint_id: string;
  event: string;
  payload: Record<string, unknown>;
  status: string;
  attempts: number;
  max_attempts: number;
  next_attempt_at: string;
  response_status: number | null;
  error_code: string | null;
  error_message: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface AuditLog {
  id: string;
  user_id: string | null;
  action: string;
  account_id: string | null;
  metadata: Record<string, unknown>;
  ip: string | null;
  created_at: string;
}

export interface AuditLogPage {
  items: AuditLog[];
  next_cursor: string | null;
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKey {
  key: string;
}
