// Client API minimal (fetch) + gestion du jeton en localStorage.
import type { Cluster, Theme, Token, Usage, User } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

const TOKEN_KEY = "news_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth = true,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  // La réponse n'est pas toujours du JSON (ex. erreur 500 en texte brut de uvicorn).
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : "") ||
      text?.slice(0, 200) ||
      res.statusText;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

// --- Auth ---
export const api = {
  register: (email: string, password: string, display_name: string) =>
    request<Token>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    }, false),

  login: (email: string, password: string) =>
    request<Token>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }, false),

  me: () => request<User>("/auth/me"),

  // --- Themes ---
  listThemes: () => request<Theme[]>("/themes"),
  createTheme: (
    name: string,
    description: string,
    scan_interval_hours: number,
    lookback_hours: number,
  ) =>
    request<Theme>("/themes", {
      method: "POST",
      body: JSON.stringify({ name, description, scan_interval_hours, lookback_hours }),
    }),
  updateTheme: (id: number, patch: Partial<Theme>) =>
    request<Theme>(`/themes/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteTheme: (id: number) =>
    request<void>(`/themes/${id}`, { method: "DELETE" }),
  scanTheme: (id: number) =>
    request(`/themes/${id}/scan`, { method: "POST" }),

  // --- News ---
  feed: (themeId?: number) =>
    request<Cluster[]>(themeId ? `/news?theme_id=${themeId}` : "/news"),

  // --- Usage (credits sources de recherche) ---
  usage: () => request<Usage>("/usage"),
};
