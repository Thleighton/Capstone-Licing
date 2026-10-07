// Verifica la sesión emitida por el proyecto Supabase "Licing/Usuarios" y que el
// perfil (public.usuario) exista y esté activo. Lo usan las rutas de api/ que leen
// "Licing/Datos". Los archivos que empiezan con "_" no son rutas en Vercel.

const CACHE_MS = 60 * 1000; // evita validar el mismo token en cada petición paralela
const cache = new Map();

function httpError(status, message) {
  const e = new Error(message);
  e.status = status;
  return e;
}

async function usuarioDesdeRequest(req) {
  const h = req.headers.authorization || "";
  const token = h.startsWith("Bearer ") ? h.slice(7).trim() : "";
  if (!token) throw httpError(401, "Debes iniciar sesión");

  const base = process.env.USUARIOS_URL, key = process.env.USUARIOS_ANON_KEY;
  if (!base || !key) throw httpError(500, "Faltan USUARIOS_URL / USUARIOS_ANON_KEY en las variables de entorno");

  const hit = cache.get(token);
  if (hit && hit.hasta > Date.now()) return hit.perfil;

  const headers = { apikey: key, Authorization: "Bearer " + token };
  const r = await fetch(base + "/auth/v1/user", { headers });
  if (!r.ok) throw httpError(401, "Sesión inválida o expirada");
  const user = await r.json();

  // RLS de Licing/Usuarios permite a cada usuario leer su propia fila
  const p = await fetch(base + "/rest/v1/usuario?select=id,nombre,email,rol,activo&id=eq." + encodeURIComponent(user.id), { headers });
  const [perfil] = p.ok ? await p.json() : [];
  if (!perfil) throw httpError(403, "Tu usuario no tiene perfil en LICING");
  if (!perfil.activo) throw httpError(403, "Tu cuenta está desactivada. Contacta al administrador.");

  if (cache.size > 500) cache.clear();
  cache.set(token, { perfil, hasta: Date.now() + CACHE_MS });
  return perfil;
}

module.exports = { usuarioDesdeRequest, httpError };
