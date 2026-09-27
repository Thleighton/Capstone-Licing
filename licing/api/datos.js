// Lectura de "Licing/Datos" para el dashboard, solo con sesión válida de "Licing/Usuarios".
//   GET /api/datos?t=<tabla>&q=<query string de PostgREST codificado>
// Solo lectura (GET), solo tablas de la lista blanca (también en recursos embebidos).
// Usa la service_role en el servidor: el navegador ya no necesita ninguna key de Datos.
const { usuarioDesdeRequest } = require("./_auth");

const TABLAS = new Set(["licitacion", "licitacion_item", "requisito_extraido", "ejecucion_busqueda", "organismo"]);

function embebidas(select) {
  // "organismo(nombre)", "alias:organismo(...)", "organismo!fk(...)"
  return [...String(select || "").matchAll(/([a-z_][a-z0-9_]*)\s*(?:![a-z0-9_]+)?\s*\(/gi)].map(m => m[1].toLowerCase());
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "GET") return res.status(405).json({ error: "Solo lectura" });

  try { await usuarioDesdeRequest(req); }
  catch (e) { return res.status(e.status || 500).json({ error: e.message }); }

  const tabla = String(req.query?.t || "");
  const qs = String(req.query?.q || "");
  if (!TABLAS.has(tabla)) return res.status(400).json({ error: "Tabla no permitida: " + tabla });
  const noPermitidas = embebidas(new URLSearchParams(qs).get("select")).filter(t => !TABLAS.has(t));
  if (noPermitidas.length) return res.status(400).json({ error: "Relación no permitida: " + noPermitidas.join(", ") });

  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!process.env.SUPABASE_URL || !key) return res.status(500).json({ error: "Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY" });

  const headers = { apikey: key, Authorization: "Bearer " + key };
  if (/count=exact/.test(req.headers.prefer || "")) headers.Prefer = "count=exact";
  if (/^\d+-\d+$/.test(req.headers.range || "")) headers.Range = req.headers.range;

  try {
    const r = await fetch(process.env.SUPABASE_URL + "/rest/v1/" + tabla + (qs ? "?" + qs : ""), { headers });
    const body = await r.text();
    const cr = r.headers.get("content-range");
    if (cr) {
      res.setHeader("Content-Range", cr);
      res.setHeader("Access-Control-Expose-Headers", "Content-Range");
    }
    res.statusCode = r.status;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    return res.end(body);
  } catch (e) {
    return res.status(502).json({ error: "No se pudo consultar Licing/Datos: " + e.message });
  }
};

module.exports._test = { embebidas, TABLAS };
