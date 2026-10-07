import { esNueva } from "../../../core/data/licitaciones";

export default function EstadoBadge({ r }) {
  if (r.descartada_filtro) return <span className="badge" title={r.motivo_descarte || ""}>Descartada</span>;
  const e = String(r.estado_mp || "").toLowerCase();
  if (esNueva(r) && e === "publicada") return <span className="badge blue">Nueva</span>;
  if (e === "publicada") return <span className="badge amber">Abierta</span>;
  if (e.includes("adjudic") || e === "proveedor_seleccionado") return <span className="badge green">{r.estado_mp}</span>;
  return <span className="badge">{r.estado_mp || "-"}</span>;
}
