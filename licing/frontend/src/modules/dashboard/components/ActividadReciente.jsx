import { hace } from "../../../core/ui/format";
const TITULOS = { error: "Ingesta con error", en_curso: "Ingesta en curso", completada: "Ingesta completada", parcial: "Ingesta parcial", interrumpida: "Ingesta interrumpida" };
export default function ActividadReciente({ runs }) {
  if (!runs.length) return <p className="empty">Sin ejecuciones de ingesta aún.</p>;
  return runs.map(e => <div className="act" key={e.id}>
    <span className={"dot " + (e.estado === "error" ? "bad" : e.estado === "completada" ? "" : "warn")} />
    <div className="body"><div className="head">{TITULOS[e.estado] || e.estado}<span>{hace(e.fin || e.inicio)}</span></div>
      <p>{e.descargados} descargadas, {e.procesados} procesadas{e.n_errores ? " · " + e.n_errores + " con error" : ""}{e.detenido_por_error_api ? " · detenida por límite de la API" : ""}</p></div>
  </div>);
}
