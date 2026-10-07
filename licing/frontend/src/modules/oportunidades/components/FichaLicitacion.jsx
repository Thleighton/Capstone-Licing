// Ficha de detalle de una licitación (ítems + requisitos extraídos).
import { useEffect, useState } from "react";
import { datosJson } from "../../../core/api/client";
import { useLicitaciones } from "../../../core/data/LicitacionesProvider";
import Dialog from "../../../core/ui/Dialog";
import { clp, fecha } from "../../../core/ui/format";
import { officialOpportunityUrl } from "../utils";

function Requisitos({ reqs }) {
  if (!reqs.length) return <p>No hay requisitos identificados automáticamente. Revisa las bases en la ficha de Mercado Público.</p>;
  return reqs.map((q, i) => {
    const attendees = q.n_asistentes != null && Number(q.n_asistentes) > 0;
    const services = Array.isArray(q.servicios_req) ? q.servicios_req : [];
    const review = !q.tipo_evento || !attendees || !services.length
      ? "Información incompleta; confirmar en las bases."
      : "Datos detectados automáticamente; confirmar en las bases.";
    return (
      <section className="requirement-summary" key={i}>
        <dl className="kv">
          <dt>Tipo de evento detectado</dt><dd>{q.tipo_evento || "No identificado"}</dd>
          <dt>Cantidad de asistentes</dt><dd>{attendees ? q.n_asistentes + " personas" : "No identificada"}</dd>
          <dt>Servicios detectados</dt>
          <dd>{services.length ? services.map((s, j) => (
            <span key={j} className="badge blue">{s.servicio || "Servicio sin clasificar"}
              {s.personas ? " · " + s.personas + " personas" : ""}{s.habitaciones ? " · " + s.habitaciones + " habitaciones" : ""}</span>
          )).reduce((a, b) => [a, " ", b]) : "No identificados"}</dd>
        </dl>
        <p><strong>Revisión:</strong> {review}</p>
      </section>
    );
  });
}

export default function FichaLicitacion() {
  const { rows, fichaId, cerrarFicha } = useLicitaciones();
  const r = rows.find(x => x.id == fichaId);
  const [detalle, setDetalle] = useState(null); // { items, reqs } | { error }

  useEffect(() => {
    if (!fichaId) return;
    let vivo = true;
    setDetalle(null);
    Promise.all([
      datosJson("licitacion_item?licitacion_id=eq." + fichaId + "&order=correlativo"),
      datosJson("requisito_extraido?licitacion_id=eq." + fichaId),
    ]).then(([items, reqs]) => vivo && setDetalle({ items, reqs }))
      .catch(e => vivo && setDetalle({ error: e.message }));
    return () => { vivo = false; };
  }, [fichaId]);

  const url = r ? officialOpportunityUrl(r) : null;
  return (
    <Dialog id="dlg" open={Boolean(r)} onClose={cerrarFicha}>
      {r && <>
        <div className="dlg-head">
          <div><div className="code">{r.codigo_mp}</div><strong>{r.nombre}</strong></div>
          <button onClick={cerrarFicha}>Cerrar</button>
        </div>
        <div className="detail-source">
          {url ? <><a className="button primary" href={url} target="_blank" rel="noopener noreferrer">Abrir en Mercado Público ↗</a>
            <p className="sub">Ficha oficial · se abre en una pestaña nueva.</p></>
            : <p className="sub">No hay un enlace oficial disponible para este registro.</p>}
        </div>
        <div className="dlg-body">
          {!detalle ? "Cargando..." : detalle.error ? "Error: " + detalle.error : <>
            <dl className="kv">
              <dt>Organismo</dt><dd>{r.organismo?.nombre} - {r.organismo?.unidad_compra}</dd>
              <dt>Ubicación</dt><dd>{r.organismo?.comuna}, {r.organismo?.region}</dd>
              <dt>Tipo</dt><dd>{r.tipo}</dd>
              <dt>Publicación</dt><dd>{fecha(r.fecha_publicacion)}</dd>
              <dt>Cierre</dt><dd>{fecha(r.fecha_cierre)}</dd>
              <dt>Monto estimado</dt><dd>{clp(r.monto_estimado)}</dd>
              <dt>Oferentes</dt><dd>{r.n_oferentes ?? "-"}</dd>
              {r.motivo_descarte && <><dt>Motivo descarte</dt><dd>{r.motivo_descarte}</dd></>}
            </dl>
            <h3>Descripción</h3><p>{r.descripcion}</p>
            <h3>Ítems ({detalle.items.length})</h3>
            <table><thead><tr><th>#</th><th>Producto</th><th>Descripción</th><th>Adjudicado a</th><th>Monto unit.</th></tr></thead>
              <tbody>{detalle.items.map(i => (
                <tr key={i.id ?? i.correlativo}><td>{i.correlativo}</td><td>{i.nombre_producto}</td><td>{i.descripcion}</td>
                  <td>{i.adj_nombre_proveedor || "-"}</td><td>{clp(i.adj_monto_unitario)}</td></tr>
              ))}</tbody></table>
            <h3>Requisitos extraídos</h3>
            <Requisitos reqs={detalle.reqs} />
          </>}
        </div>
      </>}
    </Dialog>
  );
}
