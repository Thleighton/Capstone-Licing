import { useEffect, useId, useState } from "react";
import { apiJson } from "../../../core/api/client";
import Icon from "../../../core/ui/Icon";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import { dinero, fecha } from "../../../core/ui/format";
import { abrirCompraAgil } from "../store";
import { plazo, useResumenComprasAgiles } from "../comun";
import "../compras-agiles.css";

const PESTAÑAS = [
  { estado: "preseleccionada", nombre: "Posibles oportunidades" },
  { estado: "revision_manual", nombre: "Revisión necesaria" },
];
const VISIBLES = 6;

// Apartado de Compras Ágiles del dashboard: indicadores y las próximas en cerrar por clasificación.
export default function PanelComprasAgiles({ version }) {
  const { resumen, error } = useResumenComprasAgiles(version);
  const [pestaña, setPestaña] = useState("preseleccionada");
  const [lista, setLista] = useState({ filas: [], total: 0, cargando: true, error: "" });
  const id = useId();
  useEffect(() => {
    const control = new AbortController();
    setLista(l => ({ ...l, cargando: true }));
    apiJson(`/api/compras-agiles/preseleccion?clasificacion=${pestaña}&limite=${VISIBLES}`, { signal: control.signal })
      .then(r => setLista({ filas: r.filas, total: r.total, cargando: false, error: "" }))
      .catch(e => { if (!control.signal.aborted) setLista({ filas: [], total: 0, cargando: false, error: e.message }); });
    return () => control.abort();
  }, [pestaña, version]);
  const pre = resumen?.preseleccion;
  const conteo = { preseleccionada: pre?.preseleccionada, revision_manual: pre?.revision_manual };
  function mover(e, indice) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const destino = PESTAÑAS[(indice + 1) % PESTAÑAS.length].estado;
    setPestaña(destino);
    document.getElementById(`${id}-${destino}`)?.focus();
  }
  return <section className="card panel dashboard-panel panel-violet ca-panel" aria-labelledby={`${id}-titulo`}>
    <div className="section-title dashboard-panel-heading">
      <div className="panel-title"><span className="panel-icon tone-violet"><Icon name="bolt" /></span>
        <div><h2 id={`${id}-titulo`}>Compras Ágiles</h2><p className="sub">Cotizaciones rápidas: suelen cerrar en pocos días.</p></div></div>
      <a href="#compras-agiles">Ver todas →</a>
    </div>
    {error && <p className="msg err" role="alert">No se pudo cargar el resumen de Compras Ágiles. {error}</p>}
    <dl className="ca-mini">
      <div><dt>Abiertas</dt><dd>{resumen?.abiertas ?? "–"}</dd></div>
      <div><dt>Incorporadas hoy</dt><dd>{resumen?.nuevas ?? "–"}</dd></div>
      <div data-tono="amber"><dt>Cierran en 24 h</dt><dd>{resumen?.cierran_pronto ?? "–"}</dd></div>
      <div data-tono="green"><dt>Posibles oportunidades</dt><dd>{pre?.preseleccionada ?? "–"}</dd></div>
    </dl>
    {resumen && !resumen.carga_inicial_completa && <p className="ca-aviso" role="status"><Icon name="clock" />Carga inicial en curso: las Compras Ágiles se incorporan de a poco en cada turno.</p>}
    <div className="ca-tabs ca-tabs-panel" role="tablist" aria-label="Clasificación de Compras Ágiles">{PESTAÑAS.map((p, i) => <button
      key={p.estado} id={`${id}-${p.estado}`} type="button" role="tab" aria-selected={pestaña === p.estado}
      aria-controls={`${id}-lista`} tabIndex={pestaña === p.estado ? 0 : -1}
      onClick={() => setPestaña(p.estado)} onKeyDown={e => mover(e, i)}>
      {p.nombre}<span className="ca-count">{conteo[p.estado] ?? "–"}</span></button>)}</div>
    <div id={`${id}-lista`} role="tabpanel" aria-labelledby={`${id}-${pestaña}`} aria-busy={lista.cargando}>
      {lista.error ? <p className="empty" role="alert">No se pudo consultar la preselección. {lista.error}</p>
        : lista.cargando && !lista.filas.length ? <p className="empty">Cargando Compras Ágiles…</p>
        : !lista.filas.length ? <p className="empty">{pestaña === "preseleccionada" ? "No hay Compras Ágiles abiertas que cumplan los tres pilares." : "No hay Compras Ágiles pendientes de revisión."}</p>
        : <div className="ca-lista">{lista.filas.map(f => {
          const aviso = plazo(f.fecha_cierre);
          return <article className="ca-item" data-estado={f.estado_seleccion} key={f.id}>
            <div className="ca-item-head">
              {f.url_oficial ? <a href={f.url_oficial} target="_blank" rel="noopener noreferrer" aria-label={`Ver Compra Ágil ${f.codigo_externo} en Mercado Público`}>{f.codigo_externo} ↗</a> : <span>{f.codigo_externo}</span>}
              {aviso && <span className="ca-plazo" data-nivel={aviso.nivel}>{aviso.texto}</span>}
            </div>
            <ClienteImportanteBadge clientes={f.clientes_importantes} mostrarNombre={false} />
            <TituloLicitacion licitacion={f} className="ca-item-title" />
            <div className="ca-item-foot">
              <span>{f.monto_disponible_clp == null ? "Presupuesto no informado" : dinero(f.monto_disponible_clp, "CLP")} · cierra {fecha(f.fecha_cierre)}</span>
              <button type="button" onClick={() => abrirCompraAgil(f.id)}>Ver ficha</button>
            </div>
          </article>;
        })}</div>}
      {lista.total > VISIBLES && <p className="sub ca-mas">Se muestran las {VISIBLES} que cierran antes de {lista.total}. <a href="#compras-agiles">Ver todas</a></p>}
    </div>
  </section>;
}
