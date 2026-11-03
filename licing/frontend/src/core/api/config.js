import { detalleRespuesta, mensajeConexion, mensajeHttp } from "./httpErrors";

// Configuración pública que entrega el backend (GET /api/config):
// URL y anon key del proyecto Supabase Usuarios para iniciar sesión.
let cache = null;

export async function cargarConfig() {
  if (cache) return cache;
  try {
    const r = await fetch("/api/config", { cache: "no-store" });
    if (!r.ok) {
      const detalle = detalleRespuesta(await r.clone().json().catch(() => ({})));
      return { configured: false, error: mensajeHttp(r.status, detalle) };
    }
    const configuracion = await r.json();
    if (!configuracion || typeof configuracion !== "object" || Array.isArray(configuracion)) {
      return { configured: false, error: "LICING respondió con una configuración inválida. Recarga la aplicación." };
    }
    cache = configuracion;
  } catch (error) {
    return { configured: false, error: mensajeConexion(error) };
  }
  cache.configured = Boolean(cache.USUARIOS_URL && cache.USUARIOS_KEY);
  return cache;
}

export const getConfig = () => cache || { configured: false };
