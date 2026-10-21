import { esAbierta } from "../../../core/data/licitaciones";
export default function EstadoBadge({ r }) {
  if (esAbierta(r)) return <span className="badge amber">Abierta</span>;
  const adjudicada = String(r.estado || "").toLowerCase().includes("adjudic");
  const vencida = String(r.estado || "").toLowerCase() === "publicada" && r.fecha_cierre && new Date(r.fecha_cierre) < new Date();
  return <span className={"badge" + (adjudicada ? " green" : "")}>{vencida ? "Cierre vencido" : r.estado || "Sin estado"}</span>;
}
