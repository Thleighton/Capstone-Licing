// Sesión con Supabase Auth del proyecto "Licing/Usuarios" (sin SDK, vía REST).
// Mismo comportamiento que tenía el index.html original.
import { getConfig } from "../api/config";

const SESION_KEY = "licing-sesion";
let sesion = null;
let refrescando = null;

export const ROLES = { encargado_licitaciones: "Encargado de Licitaciones", administrador: "Administrador" };

export function leerSesion() {
  try { sesion = JSON.parse(localStorage.getItem(SESION_KEY)); } catch (_) { sesion = null; }
  return sesion;
}
export function guardarSesion(s) {
  sesion = s;
  try { s ? localStorage.setItem(SESION_KEY, JSON.stringify(s)) : localStorage.removeItem(SESION_KEY); } catch (_) { /* solo en memoria */ }
}
export const sesionActual = () => sesion;

export function normSesion(d) {
  return {
    access_token: d.access_token, refresh_token: d.refresh_token,
    expires_at: Number(d.expires_at) || Math.floor(Date.now() / 1000) + (Number(d.expires_in) || 3600),
  };
}

function jwtSub(token) {
  try { return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).sub; } catch (_) { return null; }
}

function errorAuth(d) {
  const m = d.error_description || d.msg || d.message || d.error || "Error de autenticación";
  if (/invalid login credentials/i.test(m)) return "Correo o contraseña incorrectos.";
  if (/email not confirmed/i.test(m)) return "Debes confirmar tu correo antes de ingresar.";
  if (/should be at least|weak password/i.test(m)) return "La contraseña es muy débil: usa al menos 8 caracteres.";
  if (/different from the old/i.test(m)) return "La nueva contraseña debe ser distinta de la anterior.";
  if (/rate limit|too many|security purposes/i.test(m)) return "Demasiados intentos. Espera un momento e inténtalo de nuevo.";
  return m;
}

export async function auth(path, { method = "POST", body, token } = {}) {
  const { USUARIOS_URL, USUARIOS_KEY } = getConfig();
  const res = await fetch(USUARIOS_URL + "/auth/v1/" + path, {
    method,
    headers: { apikey: USUARIOS_KEY, "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorAuth(data));
  return data;
}

export function refrescar() {
  if (!sesion?.refresh_token) return Promise.resolve(null);
  // Una sola renovación aunque haya varias consultas en paralelo (el refresh token rota)
  return (refrescando ||= auth("token?grant_type=refresh_token", { body: { refresh_token: sesion.refresh_token } })
    .then(d => { guardarSesion(normSesion(d)); return sesion.access_token; })
    .catch(() => { guardarSesion(null); return null; })
    .finally(() => { refrescando = null; }));
}

export async function tokenVigente() {
  if (!sesion?.access_token) return null;
  if (sesion.expires_at - 60 > Date.now() / 1000) return sesion.access_token;
  return refrescar();
}

export async function cargarPerfil(token) {
  const { USUARIOS_URL, USUARIOS_KEY } = getConfig();
  const id = jwtSub(token);
  const res = await fetch(USUARIOS_URL + "/rest/v1/usuario?select=id,nombre,email,rol,activo&id=eq." + encodeURIComponent(id),
    { headers: { apikey: USUARIOS_KEY, Authorization: "Bearer " + token } });
  if (!res.ok) throw new Error("No se pudo leer tu perfil (HTTP " + res.status + ").");
  return (await res.json())[0] || null;
}

// Enlaces de invitación o recuperación: Supabase vuelve con #access_token=...&type=invite|recovery
export function capturarHashAuth() {
  const h = new URLSearchParams(location.hash.slice(1));
  if (!h.has("access_token") && !h.has("error")) return null;
  history.replaceState(null, "", location.pathname + "#dashboard");
  if (h.has("error")) {
    const d = h.get("error_description") || h.get("error");
    return { error: /expired|invalid/i.test(d) ? "El enlace expiró o ya fue usado. Pide uno nuevo." : d };
  }
  guardarSesion(normSesion(Object.fromEntries(h)));
  return { tipo: h.get("type") };
}
