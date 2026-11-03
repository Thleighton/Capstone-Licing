import { forwardRef, useEffect, useId, useImperativeHandle, useState } from "react";
import { apiJson } from "../../../core/api/client";
import Icon from "../../../core/ui/Icon";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import { dinero } from "../../../core/ui/format";
import { abrirCompraAgil } from "../store";
import { useActualizarComprasAgiles, useResumenComprasAgiles } from "../comun";
import PreseleccionControles from "../../../core/ui/PreseleccionControles";
import EstadoPlazo from "../../../core/ui/EstadoPlazo";
import CierrePlazo from "../../../core/ui/CierrePlazo";
import UltimaBusqueda from "../../../core/ui/UltimaBusqueda";
import "../compras-agiles.css";

const VISIBLES = 6;

// Apartado de Compras Ágiles: oportunidades y revisiones ordenadas por cierre.
export default forwardRef(function PanelComprasAgiles({ version, integrado = false }, ref) {
  const { versionDatos, actualizando, errorActualizacion, pendientes, actualizar } = useActualizarComprasAgiles(version);
  useImperativeHandle(ref, () => ({ actualizar }), [actualizar]);
  const { resumen, error } = useResumenComprasAgiles(versionDatos);
  const [pestaña, setPestaña] = useState("preseleccionada");
  const [lista, setLista] = useState({ filas: [], total: 0, cargando: true, error: "" });
  const id = useId();
  useEffect(() => {
    const control = new AbortController();
    setLista(l => ({ ...l, cargando: true }));
    const parametros = new URLSearchParams({ clasificacion: pestaña, limite: String(VISIBLES) });
    apiJson(`/api/compras-agiles/preseleccion?${parametros}`, { signal: control.signal })
      .then(r => setLista({ filas: r.filas, total: r.total, cargando: false, error: "" }))
      .catch(e => { if (!control.signal.aborted) setLista({ filas: [], total: 0, cargando: false, error: e.message }); });
    return () => control.abort();
  }, [pestaña, versionDatos]);
  const Contenedor = integrado ? "div" : "section";
  return <Contenedor className={integrado ? "ca-panel-content" : "card panel dashboard-panel panel-violet ca-panel"}
    aria-labelledby={integrado ? undefined : `${id}-titulo`}>
    {!integrado && <div className="section-title dashboard-panel-heading">
      <div className="panel-title"><span className="panel-icon tone-violet"><Icon name="bolt" /></span>
        <div><h2 id={`${id}-titulo`}>Compras Ágiles</h2><p className="sub">Cotizaciones rápidas: suelen cerrar en pocos días.</p></div></div>
      <a href="#compras-agiles">Ver todas →</a>
    </div>}
    {error && <p className="msg err" role="alert">No se pudo cargar el resumen de Compras Ágiles. {error}</p>}
    {integrado && <><UltimaBusqueda fuente="compra_agil" /><p className="pre-nota" role="note">Se muestran procesos disponibles; revisa la etiqueta de estado y el plazo para saber si aún aceptan ofertas.</p></>}
    {resumen && !resumen.carga_inicial_completa && <p className="ca-aviso" role="status"><Icon name="clock" />Carga inicial en curso: las Compras Ágiles se incorporan de a poco en cada turno.</p>}
    <PreseleccionControles clasificacion={pestaña} total={lista.total} onClasificacion={setPestaña} mostrarFechas={false} />
    {!integrado && <button type="button" onClick={actualizar} disabled={actualizando}>{actualizando ? "Actualizando…" : "Actualizar preselección"}</button>}
    {pendientes > 0 && !actualizando && <p className="sub" role="status">{pendientes} Compras Ágiles necesitan actualizar su evaluación.</p>}
    {errorActualizacion && <p className="msg err" role="alert">No se pudo actualizar la preselección. {errorActualizacion}</p>}
    <div id={`${id}-lista`} role="region" aria-label="Resultados de Compras Ágiles" aria-busy={lista.cargando || actualizando}>
      {lista.error ? <p className="empty" role="alert">No se pudo consultar la preselección. {lista.error}</p>
        : (lista.cargando || actualizando) && !lista.filas.length ? <p className="empty" role="status">{actualizando ? "Actualizando la preselección de Compras Ágiles…" : "Cargando Compras Ágiles…"}</p>
        : !lista.filas.length ? <p className="empty">{pestaña === "preseleccionada" ? "No hay posibles oportunidades en esta carga. Puedes consultar Revisión necesaria o Todas." : "No hay Compras Ágiles en esta vista."}</p>
        : <div className="ca-lista">{lista.filas.map(f => {
          return <article className="ca-item" data-estado={f.estado_seleccion} key={f.id}>
            <div className="ca-item-head">
              <span className="ca-codigo-estado">{f.url_oficial ? <a href={f.url_oficial} target="_blank" rel="noopener noreferrer" aria-label={`Ver Compra Ágil ${f.codigo_externo} en Mercado Público`}>{f.codigo_externo} ↗</a> : <span>{f.codigo_externo}</span>}<EstadoPlazo fila={f} /></span>
            </div>
            <ClienteImportanteBadge clientes={f.clientes_importantes} mostrarNombre={false} />
            <TituloLicitacion licitacion={f} className="ca-item-title" />
            <div className="ca-item-foot">
              <div className="ca-item-resumen">
                <span>{f.monto_disponible_clp == null ? "Presupuesto no informado" : dinero(f.monto_disponible_clp, "CLP")}</span>
                <CierrePlazo fechaCierre={f.fecha_cierre} />
              </div>
              <button type="button" onClick={() => abrirCompraAgil(f.id)}>Ver ficha</button>
            </div>
          </article>;
        })}</div>}
      {lista.total > VISIBLES && <p className="sub ca-mas">Se muestran las {VISIBLES} que cierran antes de {lista.total}. <a href="#compras-agiles">Ver todas</a></p>}
    </div>
  </Contenedor>;
});
