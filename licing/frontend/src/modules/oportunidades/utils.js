// Enlace a la ficha oficial en Mercado Público (solo dominios mercadopublico.cl).
export function officialOpportunityUrl(r) {
  const code = String(r.codigo_mp || "").trim();
  // Las cotizaciones COT tienen su propia ficha pública, distinta de una licitación.
  if (/^\d+-\d+-COT\d+$/i.test(code)) return "https://buscador.mercadopublico.cl/ficha?code=" + encodeURIComponent(code);
  try {
    const url = new URL(r.url);
    if (url.protocol === "https:" && (url.hostname === "mercadopublico.cl" || url.hostname.endsWith(".mercadopublico.cl")) && !url.username && !url.password) return url.href;
  } catch (_) { /* url inválida */ }
  if (/^\d+-\d+-[A-Z]+\d+$/i.test(code) && r.tipo === "licitacion")
    return "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=" + encodeURIComponent(code);
  return null;
}

export const tipoLegible = t => (t === "compra_agil" ? "compra ágil" : t);
