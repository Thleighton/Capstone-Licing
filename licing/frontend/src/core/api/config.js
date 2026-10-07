// Configuración pública que entrega el backend (GET /api/config):
// URL y anon key del proyecto Supabase "Licing/Usuarios" para iniciar sesión.
let cache = null;

export async function cargarConfig() {
  if (cache) return cache;
  try {
    const r = await fetch("/api/config", { cache: "no-store" });
    cache = r.ok ? await r.json() : {};
  } catch (_) {
    cache = {};
  }
  cache.configured = Boolean(cache.USUARIOS_URL && cache.USUARIOS_KEY);
  return cache;
}

export const getConfig = () => cache || { configured: false };
