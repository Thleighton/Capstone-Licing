import { hace } from "../../../core/ui/format";

export default function ActividadReciente({ runs }) {
  if (!runs.length) return <p className="empty">Sin sincronizaciones aún.</p>;
  return runs.map((e, i) => {
    const tono = e.estado === "error" ? "bad" : e.estado === "en_curso" ? "warn" : "";
    const titulo = e.estado === "error" ? "Sincronización con error" : e.estado === "en_curso" ? "Sincronización en curso" : "Sincronización completada";
    const detalle = e.error ? e.error.split("\n")[0] : e.n_obtenidas + " encontradas, " + e.n_nuevas + " nuevas (" + (e.disparo === "cron" ? "automática" : "manual") + ")";
    return (
      <div className="act" key={i}><span className={"dot " + tono} />
        <div className="body"><div className="head">{titulo}<span>{hace(e.fin || e.inicio)}</span></div><p>{detalle}</p></div>
      </div>
    );
  });
}
