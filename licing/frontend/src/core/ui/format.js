// Utilidades de formato compartidas por todos los módulos.
export const DIA = 86400000;

export const clp = n =>
  n == null ? "-" : new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 }).format(n);

export const fecha = d =>
  d ? new Date(d).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" }) : "-";

export const fechaCorta = d => (d ? new Date(d).toLocaleDateString("es-CL") : "-");

export function hace(d) {
  const s = Math.max(0, (Date.now() - new Date(d)) / 1000);
  if (s < 60) return "Hace un momento";
  if (s < 3600) return "Hace " + Math.floor(s / 60) + " min";
  if (s < 86400) return "Hace " + Math.floor(s / 3600) + " h";
  return "Hace " + Math.floor(s / 86400) + " d";
}

export const normalizar = s =>
  String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim().replace(/\s+/g, " ");
