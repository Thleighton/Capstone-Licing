// Cliente HTTP del backend LICING. Todos los módulos deben pasar por aquí:
// agrega el token de sesión, lo renueva si expiró y vuelve al login si no hay acceso.
import { refrescar, tokenVigente } from "../auth/session";

let onSinSesion = () => {};
export const setOnSinSesion = fn => { onSinSesion = fn; };

/** Llamada genérica al backend: apiFetch("/api/analisis/...", { method: "POST", body }) */
export async function apiFetch(url, { headers = {}, body, method = "GET", reintento = true } = {}) {
  const token = await tokenVigente();
  if (!token) { onSinSesion("Tu sesión expiró. Vuelve a ingresar.", true); throw new Error("Sesión expirada"); }
  const res = await fetch(url, {
    method,
    headers: { ...headers, Authorization: "Bearer " + token, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && reintento && await refrescar()) return apiFetch(url, { headers, body, method, reintento: false });
  if (res.status === 401 || res.status === 403) {
    const m = (await res.clone().json().catch(() => ({}))).error;
    onSinSesion(m || "Debes iniciar sesión.", res.status === 401);
    throw new Error(m || "Sin acceso");
  }
  if (!res.ok) {
    let detail = "";
    try { const j = await res.json(); detail = j.message || j.error || j.detail || ""; } catch (_) {}
    throw new Error("HTTP " + res.status + (detail ? " - " + detail : ""));
  }
  return res;
}

/**
 * Lectura de tablas de "Licing/Datos" vía /api/datos (solo lectura, lista blanca).
 * path con sintaxis PostgREST: "licitacion?select=id,nombre&limit=10"
 */
export function datos(path, headers = {}) {
  const i = path.indexOf("?");
  const url = "/api/datos?t=" + encodeURIComponent(i < 0 ? path : path.slice(0, i)) +
              "&q=" + encodeURIComponent(i < 0 ? "" : path.slice(i + 1));
  return apiFetch(url, { headers });
}

export const datosJson = path => datos(path).then(r => r.json());

export async function contar(tabla) {
  const res = await datos(tabla + "?select=id", { Prefer: "count=exact", Range: "0-0" });
  return Number((res.headers.get("content-range") || "*/0").split("/")[1]) || 0;
}
