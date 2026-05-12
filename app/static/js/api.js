const API_BASE = "/api";
const TOKEN_KEY = "hotel-token";
const USER_KEY = "hotel-usuario";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || null;
  } catch (_e) {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch (_e) {
    /* ignore */
  }
}

export function getUsuario() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_e) {
    return null;
  }
}

export function setUsuario(usuario) {
  try {
    if (usuario) localStorage.setItem(USER_KEY, JSON.stringify(usuario));
    else localStorage.removeItem(USER_KEY);
  } catch (_e) {
    /* ignore */
  }
}

export function clearSession() {
  setToken(null);
  setUsuario(null);
}

export function redirectToLogin() {
  clearSession();
  if (!window.location.pathname.endsWith("/login.html") &&
      window.location.pathname !== "/login") {
    window.location.href = "/login.html";
  }
}

async function request(method, endpoint, data) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const options = { method, headers };
  if (data !== undefined && data !== null) {
    options.body = JSON.stringify(data);
  }
  const response = await fetch(`${API_BASE}${endpoint}`, options);
  if (response.status === 401) {
    redirectToLogin();
    throw new Error("Sesión expirada");
  }
  if (response.status === 403) {
    const text = await response.json().catch(() => ({}));
    throw new Error(text.detail || "Acceso denegado para este rol");
  }
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text();
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail || payload.message : payload;
    throw new Error(detail || `Error ${response.status}`);
  }
  return payload;
}

export async function get(endpoint) {
  return request("GET", endpoint);
}

export async function post(endpoint, data) {
  return request("POST", endpoint, data);
}

export async function put(endpoint, data) {
  return request("PUT", endpoint, data);
}

export async function patch(endpoint, data) {
  return request("PATCH", endpoint, data);
}

export async function del(endpoint) {
  return request("DELETE", endpoint);
}

export function formatBs(value) {
  const n = Number(value || 0);
  return `Bs ${n.toLocaleString("es-VE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatUsd(value) {
  const n = Number(value || 0);
  return `$ ${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatRate(value) {
  const n = Number(value || 0);
  return n.toLocaleString("es-VE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const VE_TZ = "America/Caracas";

export function formatDate(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("es-VE", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: VE_TZ,
  });
}

export function formatDateOnly(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("es-VE", {
    dateStyle: "short",
    timeZone: VE_TZ,
  });
}

export function formatTimeVE(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleTimeString("es-VE", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: VE_TZ,
  });
}

export function nowVE() {
  return new Date().toLocaleString("es-VE", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: VE_TZ,
  });
}

export function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}

export function todayIso() {
  return new Date().toISOString().slice(0, 10);
}
