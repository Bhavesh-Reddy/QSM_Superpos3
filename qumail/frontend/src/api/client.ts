/**
 * Typed wrappers over the QuMail backend (M2b) HTTP API.
 *
 * Shapes here mirror `docs/api_contract.md` and the pydantic models in
 * `backend/app/api/routes_*.py` exactly — field names are not renamed.
 * This is the ONLY module allowed to call `fetch` against the backend
 * (CLAUDE.md: "keep API calls in frontend/src/api/"). No key bytes ever
 * cross this boundary — only key IDs and non-secret crypto metadata.
 */

export type SecurityLevel = 1 | 2 | 3 | 4;

export interface ETSIStatus {
  source_KME_ID: string;
  target_KME_ID: string;
  master_SAE_ID: string;
  slave_SAE_ID: string;
  key_size: number;
  stored_key_count: number;
  max_key_count: number;
  max_key_per_request: number;
  max_key_size: number;
  min_key_size: number;
}

export interface KMConnectRequest {
  base_url: string;
  sae_id: string;
  verify_tls?: boolean;
}

export interface EmailConnectRequest {
  email: string;
  password: string;
  provider?: string | null;
}

export interface EmailConnectResponse {
  connected: boolean;
  address: string;
  provider: string;
}

export interface AttachmentIn {
  filename: string;
  content_type?: string;
  /** Base64-encoded file bytes. */
  data: string;
}

export interface SendRequest {
  to: string;
  subject?: string;
  body?: string;
  level: SecurityLevel;
  attachments?: AttachmentIn[] | null;
}

export interface SendResponse {
  message_id: string;
  key_id: string | null;
  level: SecurityLevel;
}

export interface MessageSummary {
  sender: string;
  recipient: string;
  subject: string;
  timestamp: string;
  is_encrypted: boolean;
  level: SecurityLevel | null;
  algorithm: string | null;
}

export interface FetchResponse {
  messages: MessageSummary[];
}

export interface ReadRequest {
  message_id: string;
}

export interface ReadResponse {
  body: string;
  level: SecurityLevel;
  metadata: Record<string, unknown>;
}

export interface HealthResponse {
  status: string;
  version: string;
}

/** Mirrors the `{ error: { type, message } }` shape every non-2xx response shares. */
export class ApiError extends Error {
  readonly type: string;
  readonly status: number;

  constructor(type: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.type = type;
    this.status = status;
  }
}

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? DEFAULT_BASE_URL;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch {
    throw new ApiError("NetworkError", "Could not reach the QuMail backend.", 0);
  }

  if (!res.ok) {
    let type = "HTTPError";
    let message = res.statusText || `request failed with status ${res.status}`;
    try {
      const body = (await res.json()) as { error?: { type?: string; message?: string } };
      if (body?.error) {
        type = body.error.type ?? type;
        message = body.error.message ?? message;
      }
    } catch {
      // Response body wasn't JSON (or was empty) — keep the defaults above.
    }
    throw new ApiError(type, message, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function connectKm(payload: KMConnectRequest): Promise<ETSIStatus> {
  return request<ETSIStatus>("/auth/km", { method: "POST", body: JSON.stringify(payload) });
}

export function connectEmail(payload: EmailConnectRequest): Promise<EmailConnectResponse> {
  return request<EmailConnectResponse>("/auth/email", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function sendMail(payload: SendRequest): Promise<SendResponse> {
  return request<SendResponse>("/mail/send", { method: "POST", body: JSON.stringify(payload) });
}

export function fetchMail(folder = "INBOX", limit = 50): Promise<FetchResponse> {
  const params = new URLSearchParams({ folder, limit: String(limit) });
  return request<FetchResponse>(`/mail/fetch?${params.toString()}`);
}

export function readMail(payload: ReadRequest): Promise<ReadResponse> {
  return request<ReadResponse>("/mail/read", { method: "POST", body: JSON.stringify(payload) });
}

export function getKeysStatus(): Promise<ETSIStatus> {
  return request<ETSIStatus>("/keys/status");
}
