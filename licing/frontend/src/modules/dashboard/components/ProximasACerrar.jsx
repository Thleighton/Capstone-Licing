import { esCandidata } from "../../../core/data/licitaciones";
import { fecha } from "../../../core/ui/format";

export default function ProximasACerrar({ rows, estado, abrirFicha }) {
  if (estado === "err") return <p className="empty">No se pudieron cargar los datos. Pulsa Actualizar para volver a intentar.</p>;
  if (estado !== "ok") return <p className="empty">Cargando oportunidades…</p>;
  const next = rows.filter(r => esCandidata(r) && r.fecha_cierre && new Date(r.fecha_cierre) > new Date())
    .sort((a, b) => new Date(a.fecha_cierre) - new Date(b.fecha_cierre)).slice(0, 4);
  if (!next.length) return <p className="empty">No hay oportunidades vigentes próximas a cerrar en los datos consultados.</p>;
  return next.map(r => (
    <div className="preview-row" key={r.id}>
      <div><strong>{r.nombre}</strong><span className="sub">{r.codigo_mp} · Cierra {fecha(r.fecha_cierre)}</span></div>
      <button onClick={() => abrirFicha(r.id)}>Ver ficha</button>
    </div>
  ));
}
