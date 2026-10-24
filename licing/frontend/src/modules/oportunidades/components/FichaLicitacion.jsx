import { useEffect, useState } from "react";
import { apiJson } from "../../../core/api/client";
import { useLicitaciones } from "../../../core/data/LicitacionesProvider";
import Dialog from "../../../core/ui/Dialog";
import { dinero, fecha } from "../../../core/ui/format";
import { officialOpportunityUrl } from "../utils";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
export default function FichaLicitacion() {
  const { fichaId, cerrarFicha } = useLicitaciones();
  const [detalle, setDetalle] = useState(null);
  useEffect(() => {
    if (!fichaId) return;
    let vivo = true;
    setDetalle(null);
    apiJson("/api/licitaciones/" + fichaId).then(data => vivo && setDetalle({ id: fichaId, ...data }))
      .catch(e => vivo && setDetalle({ id: fichaId, error: e.message }));
    return () => { vivo = false; };
  }, [fichaId]);
  const actual = detalle?.id === fichaId ? detalle : null;
  const r = actual?.licitacion, url = r ? officialOpportunityUrl(r) : null;
  return <Dialog id="dlg" open={Boolean(fichaId)} onClose={cerrarFicha}>
    <div className="dlg-head"><div><div className="code">{r?.codigo_externo || "Licitación"}</div>{r ? <TituloLicitacion as="div" licitacion={r} /> : <strong>Detalle de la oportunidad</strong>}</div><button onClick={cerrarFicha}>Cerrar</button></div>
    {url && <div className="detail-source"><a className="button primary" href={url} target="_blank" rel="noopener noreferrer">Abrir en Mercado Público ↗</a><p className="sub">Ficha oficial · se abre en una pestaña nueva.</p></div>}
    <div className="dlg-body">{!actual ? "Cargando..." : actual.error ? <p role="alert">Error: {actual.error}</p> : <>
      <ClienteImportanteBadge clientes={r.clientes_importantes} />
      <dl className="kv">
        <dt>Organismo</dt><dd>{r.nombre_organismo || "-"}</dd><dt>Unidad compradora</dt><dd>{r.nombre_unidad || "-"}</dd>
        <dt>Ubicación del comprador</dt><dd>{[r.comuna_comprador, r.region_comprador].filter(Boolean).join(", ") || "No informada"}</dd>
        <dt>Tipo</dt><dd>{r.tipo || "No informado"}</dd>
        <dt>Estado</dt><dd>{r.estado || "-"}</dd><dt>Publicación</dt><dd>{fecha(r.fecha_publicacion)}</dd>
        <dt>Cierre</dt><dd>{fecha(r.fecha_cierre)}</dd><dt>Monto estimado</dt><dd>{dinero(r.monto_estimado, r.moneda)}</dd>
        <dt>Última consulta a la fuente</dt><dd>{fecha(r.fuente_consultada_en)}</dd>
        <dt>Tipo de estimación</dt><dd>{{1: "Presupuesto disponible", 2: "Precio referencial", 3: "No es posible estimar"}[r.estimacion] || "No informado"}</dd>
        <dt>Visibilidad del monto</dt><dd>{r.visibilidad_monto === 1 ? "Público" : r.visibilidad_monto === 0 ? "No publicado" : "No informada"}</dd>
      </dl>
      <h3>Descripción</h3><p>{r.descripcion || "Sin descripción"}</p><h3>Ítems ({actual.items.length})</h3>
      <div className="scroll"><table><thead><tr><th>Correlativo de origen</th><th>Producto</th><th>Categoría</th><th>Descripción</th><th>Cantidad</th><th>Unidad</th></tr></thead>
        <tbody>{actual.items.map(i => <tr key={i.id}><td>{i.correlativo}</td><td>{i.nombre_producto || "-"}<div className="sub">{i.codigo_producto}</div></td><td>{i.categoria || "No informada"}<div className="sub">{i.codigo_categoria}</div></td><td>{i.descripcion || "-"}</td><td>{i.cantidad ?? "-"}</td><td>{i.unidad_medida || "-"}</td></tr>)}</tbody>
      </table><p className="sub">La compatibilidad con el hotel y los requisitos deben revisarse en las bases.</p>
      </div>
    </>}</div>
  </Dialog>;
}

