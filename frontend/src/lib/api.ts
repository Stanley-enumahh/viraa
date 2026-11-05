import type {
  AssistantResult,
  AuthResponse,
  Draft,
  HistoryRange,
  Portfolio,
  Price,
  PriceHistory,
  PriceList,
  Transaction,
  User,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";
const ACCESS_KEY = "vira.access";
const REFRESH_KEY = "vira.refresh";

export class ApiError extends Error {
  status: number;
  fields: Record<string, string[]>;

  constructor(status: number, message: string, fields: Record<string, string[]> = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

function readToken(key: string) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function saveTokens(access: string, refresh?: string) {
  try {
    window.localStorage.setItem(ACCESS_KEY, access);
    if (refresh) window.localStorage.setItem(REFRESH_KEY, refresh);
  } catch {
    // Private windows can block storage. The user stays logged in until the next reload fails.
  }
}

export function clearTokens() {
  try {
    window.localStorage.removeItem(ACCESS_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
  } catch {
    // Nothing to clear.
  }
}

export function hasSession() {
  return Boolean(readToken(REFRESH_KEY));
}

const sessionExpiredListeners = new Set<() => void>();

export function onSessionExpired(listener: () => void) {
  sessionExpiredListeners.add(listener);
  return () => {
    sessionExpiredListeners.delete(listener);
  };
}

async function toApiError(response: Response) {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Not JSON, such as a server error page.
  }
  if (body && typeof body === "object") {
    const { detail } = body as { detail?: unknown };
    const fields: Record<string, string[]> = {};
    for (const [name, value] of Object.entries(body)) {
      if (name === "detail" || name === "code") continue;
      fields[name] = Array.isArray(value) ? value.map(String) : [String(value)];
    }
    const message = typeof detail === "string" ? detail : Object.values(fields)[0]?.[0];
    if (message) return new ApiError(response.status, message, fields);
  }
  return new ApiError(response.status, "Something went wrong. Please try again.");
}

let refreshing: Promise<boolean> | null = null;

function refreshAccessToken() {
  // Several polls can hit an expired token at once, so they all share one refresh.
  refreshing ??= (async () => {
    const refresh = readToken(REFRESH_KEY);
    if (!refresh) return false;
    try {
      const response = await fetch(`${API_URL}/auth/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });
      if (!response.ok) return false;
      const data = (await response.json()) as { access: string };
      saveTokens(data.access);
      return true;
    } catch {
      return false;
    }
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  authenticated?: boolean;
};

async function sendRequest(path: string, { method = "GET", body, authenticated = true }: RequestOptions = {}) {
  const send = () => {
    const headers: Record<string, string> = {};
    const isForm = body instanceof FormData;
    if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
    const token = authenticated ? readToken(ACCESS_KEY) : null;
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  };

  let response: Response;
  try {
    response = await send();
    if (response.status === 401 && authenticated) {
      if (await refreshAccessToken()) {
        response = await send();
      } else {
        clearTokens();
        sessionExpiredListeners.forEach((listener) => listener());
      }
    }
  } catch {
    throw new ApiError(0, "Can't reach Vira right now. Check that the server is running.");
  }

  if (!response.ok) throw await toApiError(response);
  return response;
}

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const response = await sendRequest(path, options);
  return (await response.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login/", { method: "POST", body: { email, password }, authenticated: false }),
  register: (payload: { email: string; username: string; full_name: string; password: string }) =>
    request<AuthResponse>("/auth/register/", { method: "POST", body: payload, authenticated: false }),
  me: () => request<User>("/auth/me/"),
  prices: () => request<PriceList>("/market/prices/", { authenticated: false }),
  price: (symbol: string) =>
    request<Price & { as_of: string }>(`/market/prices/${encodeURIComponent(symbol)}/`, { authenticated: false }),
  history: (symbol: string, range: HistoryRange) =>
    request<PriceHistory>(`/market/prices/${encodeURIComponent(symbol)}/history/?range=${range}`, {
      authenticated: false,
    }),
  portfolio: () => request<Portfolio>("/wallets/"),
  transactions: (params: { kind?: string; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.kind) query.set("kind", params.kind);
    if (params.limit) query.set("limit", String(params.limit));
    const suffix = query.size ? `?${query}` : "";
    return request<Transaction[]>(`/wallets/transactions/${suffix}`);
  },
  command: (text: string) => request<AssistantResult>("/assistant/command/", { method: "POST", body: { text } }),
  voice: (audio: Blob, wakeWord: boolean) => {
    const form = new FormData();
    form.append("audio", audio, audio.type.includes("mp4") ? "clip.mp4" : "clip.webm");
    form.append("wake_word", String(wakeWord));
    return request<AssistantResult>("/assistant/voice/", { method: "POST", body: form });
  },
  speak: async (text: string) => {
    const response = await sendRequest("/assistant/speak/", { method: "POST", body: { text } });
    return response.blob();
  },
  draft: (reference: string) => request<Draft>(`/assistant/drafts/${reference}/`),
  approveDraft: (reference: string) =>
    request<{ reply: string; draft: Draft }>(`/assistant/drafts/${reference}/approve/`, { method: "POST" }),
  rejectDraft: (reference: string) =>
    request<{ reply: string; draft: Draft }>(`/assistant/drafts/${reference}/reject/`, { method: "POST" }),
};
