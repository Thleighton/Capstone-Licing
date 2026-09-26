// Sincroniza licitaciones y compras ágiles abiertas de Mercado Público hacia Supabase.
// Se invoca por Vercel Cron (vercel.json) o a mano:
//   curl -H "Authorization: Bearer $CRON_SECRET" "https://TU-APP.vercel.app/api/sync?fuente=compra_agil"
// fuente = todas (default) | licitaciones | compra_agil

const LIC_BASE = "https://api.mercadopublico.cl/servicios/v1/publico";
const CA_BASE = "https://api2.mercadopublico.cl";

const REGIONES = {
  tarapaca: 1, antofagasta: 2, atacama: 3, coquimbo: 4, valparaiso: 5, "o'higgins": 6, ohiggins: 6,
  maule: 7, biobio: 8, araucania: 9, "los lagos": 10, aysen: 11, magallanes: 12,
  metropolitana: 13, "los rios": 14, arica: 15, nuble: 16,
};

const sleep = ms => new Promise(r => setTimeout(r, ms));
const norm = s => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const regionCodigo = nombre => {
  const n = norm(nombre);
  const k = Object.keys(REGIONES).find(k => n.includes(k));
  return k ? REGIONES[k] : null;
};

// ---------- Supabase (REST, con service_role) ----------
async function sb(path, { method = "GET", body, prefer } = {}) {
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  const res = await fetch(process.env.SUPABASE_URL + "/rest/v1/" + path, {
    method,
    headers: {
      apikey: key, Authorization: "Bearer " + key, "Content-Type": "application/json",
      ...(prefer ? { Prefer: prefer } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const txt = await res.text();
  if (!res.ok) throw new Error(`Supabase ${method} ${path.split("?")[0]} -> ${res.status} ${txt.slice(0, 300)}`);
  return txt ? JSON.parse(txt) : null;
}

// ---------- Mercado Público ----------
async function getLicitaciones(qs, intento = 0) {
  const url = `${LIC_BASE}/licitaciones.json?${qs}&ticket=${encodeURIComponent(process.env.MP_TICKET)}`;
  const res = await fetch(url);
  const data = await res.json().catch(() => null);
  // 10500 = peticiones simultáneas; reintenta una vez
  if ((!res.ok || data?.Codigo) && intento < 2) { await sleep(1500); return getLicitaciones(qs, intento + 1); }
  if (!res.ok || data?.Codigo) throw new Error(`Licitaciones API ${res.status}: ${data?.Mensaje || "sin detalle"}`);
  return data;
}

async function getCompraAgil(path) {
  const res = await fetch(CA_BASE + path, { headers: { ticket: process.env.MP_TICKET } });
  const data = await res.json().catch(() => null);
  if (res.status === 429) throw new Error("Compra Ágil: cuota diaria agotada (429)");
  if (!res.ok || data?.success === "NOK") {
    throw new Error(`Compra Ágil ${res.status}: ${data?.errors?.[0]?.mensaje || "sin detalle"}`);
  }
  return data.payload;
}

// La API entrega fechas sin zona horaria (hora de Chile). Se convierten a UTC.
function chileISO(s) {
  if (!s) return null;
  if (/[zZ]$|[+-]\d\d:?\d\d$/.test(s)) return new Date(s).toISOString();
  const naive = new Date(s + "Z");
  if (isNaN(naive) || naive.getUTCFullYear() < 2000) return null;
  const parte = new Intl.DateTimeFormat("en-US", { timeZone: "America/Santiago", timeZoneName: "longOffset" })
    .formatToParts(naive).find(p => p.type === "timeZoneName").value;
  const m = /GMT([+-])(\d\d):(\d\d)/.exec(parte);
  const offMin = m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) : 0;
  return new Date(naive.getTime() - offMin * 60000).toISOString();
}
const num = v => (v === null || v === undefined || v === "" || isNaN(Number(v))) ? null : Number(v);

// ---------- Reglas provisorias de requisitos (mismas que ingestar_mp_csv) ----------
function servicioDe(t) {
  if (/coffee/.test(t)) return "Coffee break";
  if (/almuerzo/.test(t)) return "Almuerzo";
  if (/\bcena/.test(t)) return "Cena";
  if (/c[oó]ctel|coctel/.test(t)) return "Cóctel";
  if (/alojamiento|habitaci/.test(t)) return "Alojamiento";
  if (/sal[oó]n/.test(t)) return "Arriendo de salón";
  return null;
}
function extraerRequisitos(nombre, descripcion, items) {
  const texto = [nombre, descripcion, ...items.map(i => `${i.nombre_producto} ${i.descripcion}`)].join(" ").toLowerCase();
  const personas = [...texto.matchAll(/(\d+)\s*personas/g)].map(m => Number(m[1]));
  const tipo = ["jornada", "seminario", "capacitación", "capacitacion", "taller", "congreso",
    "encuentro", "reunión", "reunion", "ceremonia", "conferencia"].find(t => texto.includes(t)) || null;
  const servicios = items.flatMap(i => {
    const d = `${i.descripcion || ""} ${i.nombre_producto || ""}`.toLowerCase();
    const s = servicioDe(d);
    if (!s) return [];
    return [{
      servicio: s, item: i.correlativo, cantidad: i.cantidad,
      personas: Number((/(\d+)\s*personas/.exec(d) || [])[1]) || null,
      habitaciones: Number((/(\d+)\s*habitaciones/.exec(d) || [])[1]) || null,
    }];
  });
  const nAsist = personas.length ? Math.max(...personas) : null;
  return {
    tipo_evento: tipo, n_asistentes: nAsist, servicios_req: servicios,
    confianza_nlp: nAsist && tipo ? 0.5 : 0.3,
  };
}

// ---------- Normalización a las tablas de licing_datos ----------
function motivosDescarte(estado, regionTxt, regionObjetivo) {
  const m = [];
  if (norm(estado) !== "publicada") m.push(`Estado '${estado}' (no abierta)`);
  if (regionObjetivo && !norm(regionTxt).includes(norm(regionObjetivo))) m.push(`Fuera de región objetivo (${regionTxt})`);
  return m;
}

function normLicitacion(l, regionObjetivo) {
  const c = l.Comprador || {}, f = l.Fechas || {}, a = l.Adjudicacion || {};
  const items = (l.Items?.Listado || []).map(i => ({
    correlativo: num(i.Correlativo), codigo_producto: String(i.CodigoProducto ?? "") || null,
    codigo_categoria: String(i.CodigoCategoria ?? "") || null, categoria: i.Categoria || null,
    nombre_producto: i.NombreProducto || null, descripcion: (i.Descripcion || "").trim() || null,
    unidad_medida: i.UnidadMedida || null, cantidad: num(i.Cantidad),
    adj_rut_proveedor: i.Adjudicacion?.RutProveedor || null,
    adj_nombre_proveedor: i.Adjudicacion?.NombreProveedor || null,
    adj_cantidad: num(i.Adjudicacion?.Cantidad), adj_monto_unitario: num(i.Adjudicacion?.MontoUnitario),
  }));
  const estado = l.Estado || "Publicada";
  const motivos = motivosDescarte(estado, c.RegionUnidad, regionObjetivo);
  const tipoMP = String(l.Tipo || "");
  return {
    org: c.RutUnidad ? {
      rut: c.RutUnidad, nombre: c.NombreOrganismo || c.NombreUnidad || "(sin nombre)",
      unidad_compra: c.NombreUnidad || null, region: c.RegionUnidad || null, comuna: c.ComunaUnidad || null,
    } : null,
    lic: {
      codigo_mp: l.CodigoExterno.trim(),
      tipo: /^L/.test(tipoMP) || tipoMP === "E2" ? "licitacion" : tipoMP === "CO" ? "compra_agil" : tipoMP === "TD" ? "trato_directo" : "otro",
      nombre: (l.Nombre || "").trim(), descripcion: (l.Descripcion || "").trim() || null,
      fecha_publicacion: chileISO(f.FechaPublicacion), fecha_cierre: chileISO(f.FechaCierre || l.FechaCierre),
      monto_estimado: num(l.MontoEstimado), moneda: l.Moneda || "CLP", estado_mp: estado,
      url: "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=" + l.CodigoExterno.trim(),
      json_raw: l, descartada_filtro: motivos.length > 0, motivo_descarte: motivos.join("; ") || null,
      fecha_adjudicacion: chileISO(a.Fecha), n_oferentes: num(a.NumeroOferentes), url_acta: a.UrlActa || null,
    },
    items,
  };
}

function normCompraAgil(d, regionObjetivo) {
  const inst = d.institucion || {}, f = d.fechas || {}, p = d.presupuesto || {};
  const items = (d.productos_solicitados || []).map((i, idx) => ({
    correlativo: idx + 1, codigo_producto: String(i.codigo_producto ?? "") || null, codigo_categoria: null,
    categoria: null, nombre_producto: i.nombre || null, descripcion: i.descripcion || null,
    unidad_medida: i.unidad_medida || null, cantidad: num(i.cantidad),
    adj_rut_proveedor: null, adj_nombre_proveedor: null, adj_cantidad: null, adj_monto_unitario: null,
  }));
  const estado = d.estado?.codigo || "publicada";
  const motivos = motivosDescarte(estado, inst.nombre_region, regionObjetivo);
  return {
    org: inst.rut ? {
      rut: inst.rut, nombre: inst.organismo_comprador || "(sin nombre)", unidad_compra: inst.unidad_compra || null,
      region: inst.nombre_region || null, comuna: null,
    } : null,
    lic: {
      codigo_mp: d.codigo, tipo: "compra_agil", nombre: (d.nombre || "").trim(),
      descripcion: (d.descripcion || "").trim() || null,
      fecha_publicacion: f.fecha_publicacion || null, fecha_cierre: f.fecha_cierre || null,
      monto_estimado: num(p.monto_disponible_clp ?? p.presupuesto_estimado), moneda: "CLP", estado_mp: estado,
      url: null, json_raw: d, descartada_filtro: motivos.length > 0, motivo_descarte: motivos.join("; ") || null,
      fecha_adjudicacion: null, n_oferentes: num(d.resumen?.total_ofertas_recibidas), url_acta: null,
    },
    items,
  };
}

// ---------- Persistencia ----------
async function guardar({ org, lic, items }, ejecucionId) {
  let organismoId = null;
  if (org) {
    const r = await sb("organismo?on_conflict=rut", {
      method: "POST", body: org, prefer: "resolution=merge-duplicates,return=representation",
    });
    organismoId = r[0].id;
  }
  const [row] = await sb("licitacion?on_conflict=codigo_mp", {
    method: "POST", prefer: "resolution=merge-duplicates,return=representation",
    body: { ...lic, organismo_id: organismoId, ejecucion_id: ejecucionId, actualizado_en: new Date().toISOString() },
  });
  await sb(`licitacion_item?licitacion_id=eq.${row.id}`, { method: "DELETE" });
  if (items.length) await sb("licitacion_item", { method: "POST", body: items.map(i => ({ ...i, licitacion_id: row.id })) });
  await sb(`requisito_extraido?licitacion_id=eq.${row.id}&validado_manual=eq.false`, { method: "DELETE" });
  await sb("requisito_extraido", {
    method: "POST", body: { licitacion_id: row.id, ...extraerRequisitos(lic.nombre, lic.descripcion, items) },
  });
}

async function codigosExistentes(codigos) {
  const set = new Set();
  for (let i = 0; i < codigos.length; i += 50) {
    const lote = codigos.slice(i, i + 50);
    const r = await sb(`licitacion?select=codigo_mp&codigo_mp=in.(${lote.map(encodeURIComponent).join(",")})`);
    r.forEach(x => set.add(x.codigo_mp));
  }
  return set;
}

// ---------- Fuentes ----------
async function syncLicitaciones(crit, ejecId, max, stats) {
  const kws = crit.keywords.map(norm);
  const lista = (await getLicitaciones("estado=activas")).Listado || [];
  const candidatas = lista.filter(l => kws.some(k => norm(l.Nombre).includes(k)));
  stats.obtenidas += candidatas.length;
  const existentes = await codigosExistentes(candidatas.map(l => l.CodigoExterno));
  const nuevas = candidatas.filter(l => !existentes.has(l.CodigoExterno)).slice(0, max);
  for (const c of nuevas) {
    try {
      await sleep(400); // la API rechaza peticiones simultáneas
      const det = (await getLicitaciones("codigo=" + encodeURIComponent(c.CodigoExterno))).Listado?.[0];
      if (!det) continue;
      const n = normLicitacion(det, crit.region);
      await guardar(n, ejecId);
      stats.nuevas++; if (!n.lic.descartada_filtro) stats.filtradas++;
    } catch (e) { stats.errores.push(`${c.CodigoExterno}: ${e.message}`); }
  }
}

async function syncCompraAgil(crit, ejecId, max, stats) {
  const reg = crit.region ? regionCodigo(crit.region) : null;
  const vistos = new Map();
  for (const kw of crit.keywords) {
    const qs = new URLSearchParams({ estado: "publicada", q: kw, tamano_pagina: "50", ordenar_por: "FechaPublicacion" });
    if (reg) qs.set("region", String(reg));
    try {
      const p = await getCompraAgil("/v2/compra-agil?" + qs);
      (p.items || []).forEach(i => vistos.set(i.codigo, i));
    } catch (e) { stats.errores.push(`búsqueda '${kw}': ${e.message}`); if (/429/.test(e.message)) break; }
  }
  stats.obtenidas += vistos.size;
  const existentes = await codigosExistentes([...vistos.keys()]);
  const nuevos = [...vistos.keys()].filter(c => !existentes.has(c)).slice(0, max);
  for (const codigo of nuevos) {
    try {
      const det = await getCompraAgil("/v2/compra-agil/" + encodeURIComponent(codigo));
      const n = normCompraAgil(det, crit.region);
      await guardar(n, ejecId);
      stats.nuevas++; if (!n.lic.descartada_filtro) stats.filtradas++;
    } catch (e) { stats.errores.push(`${codigo}: ${e.message}`); }
  }
}

// ---------- Handler ----------
module.exports = async (req, res) => {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.authorization !== `Bearer ${secret}`) return res.status(401).json({ error: "No autorizado" });
  const faltan = ["MP_TICKET", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"].filter(k => !process.env[k]);
  if (faltan.length) return res.status(500).json({ error: "Faltan variables de entorno", faltan });

  const fuente = req.query?.fuente || "todas";
  const max = Number(process.env.MAX_DETALLES) || 30;
  const stats = { obtenidas: 0, nuevas: 0, filtradas: 0, errores: [] };
  let ejecId = null;
  try {
    const criterios = await sb("criterio_busqueda?select=*&activo=eq.true&order=id");
    if (!criterios.length) throw new Error("No hay criterio_busqueda activo");
    const crit = { keywords: criterios.flatMap(c => c.keywords), region: criterios.find(c => c.region)?.region || null };
    const disparo = /vercel-cron/.test(req.headers["user-agent"] || "") ? "cron" : "manual";
    ejecId = (await sb("ejecucion_busqueda", { method: "POST", body: { disparo }, prefer: "return=representation" }))[0].id;

    if (fuente === "todas" || fuente === "licitaciones") await syncLicitaciones(crit, ejecId, max, stats).catch(e => stats.errores.push("licitaciones: " + e.message));
    if (fuente === "todas" || fuente === "compra_agil") await syncCompraAgil(crit, ejecId, max, stats).catch(e => stats.errores.push("compra_agil: " + e.message));

    const fallo = stats.errores.length > 0 && stats.nuevas === 0;
    await sb(`ejecucion_busqueda?id=eq.${ejecId}`, {
      method: "PATCH", body: {
        fin: new Date().toISOString(), estado: fallo ? "error" : "ok", n_obtenidas: stats.obtenidas,
        n_nuevas: stats.nuevas, n_filtradas: stats.filtradas, error: stats.errores.join("\n").slice(0, 2000) || null,
      },
    });
    return res.status(fallo ? 502 : 200).json({ ejecucion: ejecId, ...stats });
  } catch (e) {
    if (ejecId) await sb(`ejecucion_busqueda?id=eq.${ejecId}`, { method: "PATCH", body: { fin: new Date().toISOString(), estado: "error", error: e.message } }).catch(() => {});
    return res.status(500).json({ error: e.message, ...stats });
  }
};

module.exports._test = { chileISO, normLicitacion, normCompraAgil, extraerRequisitos, regionCodigo };
