import { esAbierta } from "../data/licitaciones";

export default function EstadoPlazo({ fila }) {
  if (esAbierta(fila)) return <span className="badge green">Abierta</span>;
  const estado = String(fila?.estado || "").trim();
  const vencida = estado.toLowerCase() === "publicada" && fila?.fecha_cierre && new Date(fila.fecha_cierre) < new Date();
  return <span className="badge">{vencida ? "Cerrada · plazo vencido" : estado || "Estado sin confirmar"}</span>;
}
