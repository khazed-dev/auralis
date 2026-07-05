export type DashboardUser = {
  id: string;
  email: string;
  name?: string | null;
  role: "platform_admin" | "admin" | "user" | "agent";
  assigned_site_ids?: string[];
  must_change_password?: boolean;
};

type TokenResponse = {
  access_token: string;
  user: DashboardUser;
};

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
export const DEV_AUTH_ENABLED =
  process.env.NODE_ENV === "development" &&
  process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";

export function getDashboardHome(role: DashboardUser["role"]): string {
  if (role === "platform_admin") return "/dashboard/team";
  if (role === "agent") return "/dashboard/handoffs";
  return "/dashboard/sites";
}

const DEV_USER: DashboardUser = {
  id: "local-development-user",
  email: "local@auralis.test",
  name: "Auralis Local",
  role: "admin",
  assigned_site_ids: [],
  must_change_password: false,
};

export function createDevSession(user: DashboardUser = DEV_USER): DashboardUser {
  localStorage.setItem("token", "auralis-local-development-token");
  localStorage.setItem("user", JSON.stringify(user));
  return user;
}

function hasDevSession() {
  return (
    DEV_AUTH_ENABLED &&
    localStorage.getItem("token") === "auralis-local-development-token"
  );
}

export function getStoredUser(): DashboardUser | null {
  try {
    const raw = localStorage.getItem("user");
    return raw ? (JSON.parse(raw) as DashboardUser) : null;
  } catch {
    return null;
  }
}

export function clearSession() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

export async function refreshSession(): Promise<DashboardUser | null> {
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) return null;
  const data = (await response.json()) as TokenResponse;
  localStorage.setItem("token", data.access_token);
  localStorage.setItem("user", JSON.stringify(data.user));
  return data.user;
}

export async function authFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  let token = localStorage.getItem("token");
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response = await fetch(input, {
    ...init,
    credentials: "include",
    headers,
  });
  if (response.status !== 401 || hasDevSession()) return response;

  const refreshed = await refreshSession();
  if (!refreshed) {
    clearSession();
    return response;
  }

  token = localStorage.getItem("token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  response = await fetch(input, {
    ...init,
    credentials: "include",
    headers,
  });
  return response;
}

export async function getCurrentUser(): Promise<DashboardUser | null> {
  if (hasDevSession()) return getStoredUser() ?? DEV_USER;

  let token = localStorage.getItem("token");
  if (!token) {
    return refreshSession();
  }

  let response = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (response.status === 401) {
    const refreshed = await refreshSession();
    if (!refreshed) return null;
    token = localStorage.getItem("token");
    response = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  }
  if (!response.ok) return null;
  const user = (await response.json()) as DashboardUser;
  localStorage.setItem("user", JSON.stringify(user));
  return user;
}

export async function logout() {
  if (hasDevSession()) {
    clearSession();
    return;
  }

  const token = localStorage.getItem("token");
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
  } finally {
    clearSession();
  }
}
