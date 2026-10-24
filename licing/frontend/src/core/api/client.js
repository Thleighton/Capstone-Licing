// Cliente HTTP del backend LICING. Todos los módulos deben pasar por aquí:
// agrega el token de sesión, lo renueva si expiró y vuelve al login si no hay acceso.
import { refrescar, tokenVigente } from "../auth/session";

let onSinSesion = () => {};
export const setOnSinSesion = fn => { onSinSesion = fn; };

/** Llamada autenticada al único backend Core. */
export async function apiFetch(url, { headers = {}, body, method = "GET", reintento = true, signal } = {}) {
  signal?.throwIfAborted();
  const token = await tokenVigente();
  signal?.throwIfAborted();
  if (!token) { onSinSesion("Tu sesión expiró. Vuelve a ingresar.", true); throw new Error("Sesión expirada"); }
  const res = await fetch(url, {
    method,
    signal,
    headers: { ...headers, Authorization: "Bearer " + token, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && reintento && await refrescar()) return apiFetch(url, { headers, body, method, reintento: false, signal });
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

export const apiJson = (url, opciones) => apiFetch(url, opciones).then(r => r.json());
