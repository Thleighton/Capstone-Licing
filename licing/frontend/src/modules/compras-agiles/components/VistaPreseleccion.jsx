import { useEffect, useState } from "react";
import { apiJson } from "../../../core/api/client";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import CierrePlazo from "../../../core/ui/CierrePlazo";
import { dinero } from "../../../core/ui/format";
import { abrirCompraAgil } from "../store";
import { ETIQUETAS, TONOS } from "../comun";
import PreseleccionControles from "../../../core/ui/PreseleccionControles";
import EstadoPlazo from "../../../core/ui/EstadoPlazo";
import PaginacionResultados from "../../../core/ui/PaginacionResultados";
import VistaTodas from "./VistaTodas";

const LIMITE = 25;

// Clasificación guardada en LicitacionesFiltradas, ordenada por cierre más próximo.
export default function VistaPreseleccion({ q = "", version, actualizando = false }) {
  const [clasificacion, setClasificacion] = useState("preseleccionada");
  const [offset, setOffset] = useState(0);
  const [busquedaId, setBusquedaId] = useState("");
  const [ordenCierre, setOrdenCierre] = useState("proximo"), [ordenPublicacion, setOrdenPublicacion] = useState("ninguna");
  const [datos, setDatos] = useState({ filas: [], total: 0, pendientes: 0 });
  const [cargando, setCargando] = useState(true), [error, setError] = useState("");
  useEffect(() => { setOffset(0); }, [q, busquedaId, clasificacion, ordenCierre, ordenPublicacion]);
  useEffect(() => {
    const control = new AbortController();
    if (!clasificacion) return () => control.abort();
    setCargando(true);
    const parametros = new URLSearchParams({ clasificacion, q, codigo: busquedaId.trim(), orden_cierre: ordenCierre, orden_publicacion: ordenPublicacion, limite: String(LIMITE), offset: String(offset) });
    apiJson("/api/compras-agiles/preseleccion?" + parametros, { signal: control.signal })
      .then(r => { setDatos(r); setError(""); })
      .catch(e => { if (!control.signal.aborted) setError(e.message); })
      .finally(() => { if (!control.signal.aborted) setCargando(false); });
    return () => control.abort();
  }, [clasificacion, q, busquedaId, ordenCierre, ordenPublicacion, offset, version]);
  const vacio = busquedaId.trim()
    ? `No hay Compras Ágiles para el ID «${busquedaId.trim()}» en esta clasificación.`
    : clasificacion === "preseleccionada"
    ? "No hay posibles oportunidades en esta carga. Puedes consultar Revisión necesaria o Todas."
    : "No hay Compras Ágiles en esta clasificación.";
  return <>
    {clasificacion ? <PreseleccionControles clasificacion={clasificacion} ordenCierre={ordenCierre} ordenPublicacion={ordenPublicacion}
      onOrdenCierre={setOrdenCierre} onOrdenPublicacion={setOrdenPublicacion} total={datos.total}
      onClasificacion={setClasificacion} entidad="Compras Ágiles" mostrarBusquedaId busquedaId={busquedaId}
      onBusquedaId={setBusquedaId} textoBusquedaId="Ej. 1195-539-COT26" ariaBusquedaId="Buscar por ID de Compra Ágil" /> : null}
    {!clasificacion ? <VistaTodas q={q} codigo={busquedaId} onCodigo={setBusquedaId} version={version} ordenCierre={ordenCierre} ordenPublicacion={ordenPublicacion}
      onOrdenCierre={setOrdenCierre} onOrdenPublicacion={setOrdenPublicacion}
      onClasificacion={setClasificacion} /> : <>
    {datos.pendientes > 0 && <p className="sub" role="status">{actualizando ? "Actualizando evaluaciones…" : `${datos.pendientes} Compras Ágiles pendientes de evaluar.`}</p>}
    <div className="scroll" aria-busy={cargando}><table className="ca-tabla">
      <colgroup><col style={{ width: 185 }} /><col /><col style={{ width: 190 }} /><col style={{ width: 135 }} /><col style={{ width: 150 }} /></colgroup>
      <thead><tr><th>Código</th><th>Compra Ágil</th><th>Cierre</th><th>Presupuesto</th><th>Preselección</th></tr></thead>
      <tbody>{datos.filas.map(f => {
        return <tr key={f.id} onClick={() => abrirCompraAgil(f.id)}
          className={f.clientes_importantes?.length ? "opportunity-important" : undefined}>
          <td><span className="ca-codigo-estado"><button className="cod" onClick={e => { e.stopPropagation(); abrirCompraAgil(f.id); }}>{f.codigo_externo}</button><EstadoPlazo fila={f} /></span>
            {f.url_oficial && <div className="sub"><a href={f.url_oficial} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>Mercado Público ↗</a></div>}</td>
          <td className="nom"><TituloLicitacion as="div" licitacion={f} />
            <ClienteImportanteBadge clientes={f.clientes_importantes} />
            <p className="ca-motivo">{f.motivo_seleccion}</p></td>
          <td><CierrePlazo fechaCierre={f.fecha_cierre} compacto /></td>
          <td>{f.monto_disponible_clp == null ? "-" : dinero(f.monto_disponible_clp, "CLP")}<div className="sub">{f.region_comprador}</div></td>
          <td><span className={"badge " + (TONOS[f.estado_seleccion] || "")}>{ETIQUETAS[f.estado_seleccion] || f.estado_seleccion}</span></td>
        </tr>;
      })}</tbody>
    </table>
    {error ? <div className="msg err" role="alert">No se pudo consultar la preselección. {error}</div>
      : cargando || actualizando ? <p className="msg" role="status">{actualizando ? "Actualizando la preselección de Compras Ágiles…" : "Cargando preselección…"}</p> : !datos.filas.length ? <p className="msg">{vacio}</p> : null}</div>
    {datos.total > 0 && <PaginacionResultados total={datos.total} offset={offset}
      limite={LIMITE} cargando={cargando || actualizando} onCambiar={setOffset} etiqueta="Páginas de Compras Ágiles" />}
    </>}
  </>;
}
