import { useEffect, useId, useRef, useState } from "react";
import { apiJson } from "../../../core/api/client";
import Icon from "../../../core/ui/Icon";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import ResultadoPreseleccion from "./ResultadoPreseleccion";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import PanelComprasAgiles from "../../compras-agiles/components/PanelDashboard";
import ResumenLicitacion from "../../oportunidades/components/ResumenLicitacion";
import PreseleccionControles, { PilaresPreseleccion } from "../../../core/ui/PreseleccionControles";
import EstadoPlazo from "../../../core/ui/EstadoPlazo";
import CierrePlazo from "../../../core/ui/CierrePlazo";
import UltimaBusqueda from "../../../core/ui/UltimaBusqueda";
import PaginacionResultados from "../../../core/ui/PaginacionResultados";
import "./preseleccion.css";

const URL = "/api/preseleccion";
const modalidades = [
  { id: "licitaciones", nombre: "Licitaciones", icono: "briefcase" },
  { id: "compras-agiles", nombre: "Compras Ágiles", icono: "bolt" },
];
const etiquetas = { preseleccionada: "Posible oportunidad", revision_manual: "Revisión necesaria", descartada: "Descartada", pendiente_evaluacion: "Sin evaluar" };
const tonos = { preseleccionada: "green", revision_manual: "amber", descartada: "", pendiente_evaluacion: "violet" };
const pilares = [
  { codigo: "vigencia", nombre: "Vigencia" },
  { codigo: "ubicacion", nombre: "Lugar del servicio" },
  { codigo: "pertinencia", nombre: "Servicio solicitado" },
];
const nombrePilar = { vigencia: "Vigencia", ubicacion: "Lugar del servicio", pertinencia: "Servicio solicitado", documentacion: "Documentación" };

export default function Preseleccion({ onActualizada, versionComprasAgiles, mostrarModalidades = false, mostrarInformacion = false, mostrarFechas = true, q = "" }) {
  const id = useId();
  const [modalidad, setModalidad] = useState("licitaciones");
  const [comprasVisitadas, setComprasVisitadas] = useState(false);
  const comprasRef = useRef(null);
  const [actualizandoCompras, setActualizandoCompras] = useState(false);
  async function actualizarCompras() {
    if (!comprasRef.current) return;
    setActualizandoCompras(true);
    try { await comprasRef.current.actualizar(); }
    finally { setActualizandoCompras(false); }
  }
  function elegirModalidad(valor) {
    setModalidad(valor);
    if (valor === "compras-agiles") setComprasVisitadas(true);
  }
  function moverModalidad(e, indice) {
    const destino = e.key === "ArrowRight" ? (indice + 1) % modalidades.length
      : e.key === "ArrowLeft" ? (indice + modalidades.length - 1) % modalidades.length
      : e.key === "Home" ? 0 : e.key === "End" ? modalidades.length - 1 : null;
    if (destino === null) return;
    e.preventDefault();
    elegirModalidad(modalidades[destino].id);
    document.getElementById(`${id}-tab-${modalidades[destino].id}`)?.focus();
  }
  const [datos, setDatos] = useState({ filas: [], total: 0, ids_fuente: [] });
  const [filtro, setFiltro] = useState("preseleccionada"); const [offset, setOffset] = useState(0);
  const [busquedaId, setBusquedaId] = useState("");
  const [ordenCierre, setOrdenCierre] = useState("proximo"), [ordenPublicacion, setOrdenPublicacion] = useState("ninguna");
  const [version, setVersion] = useState(0); const [error, setError] = useState("");
  const [errorCarga, setErrorCarga] = useState("");
  const [cargando, setCargando] = useState(true); const [ocupado, setOcupado] = useState("");
  const [seleccion, setSeleccion] = useState(null); const [detalle, setDetalle] = useState(null);
  const [errorRevision, setErrorRevision] = useState("");
  const [resumen, setResumen] = useState("");
  const secuencia = useRef(0);
  useEffect(() => {
    let vigente = true; setCargando(true);
    const control = new AbortController();
    const parametros = new URLSearchParams({ clasificacion: filtro, offset: String(offset), q, codigo: busquedaId.trim() });
    parametros.set("orden_cierre", ordenCierre); parametros.set("orden_publicacion", ordenPublicacion);
    const consulta = `${URL}?${parametros}`;
    apiJson(consulta, { signal: control.signal }).then(r => {
      if (vigente) { setDatos(r); setErrorCarga(""); }
    }).catch(e => { if (vigente) setErrorCarga(e.message); }).finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; control.abort(); };
  }, [filtro, offset, version, q, busquedaId, ordenCierre, ordenPublicacion]);
  useEffect(() => { setOffset(0); }, [q, busquedaId]);
  const actualizar = () => setVersion(v => v + 1);
  async function abrir(fila) {
    const turno = ++secuencia.current;
    setSeleccion(fila); setDetalle(null); setErrorRevision("");
    const [resultado, ficha] = await Promise.allSettled([
      apiJson(`${URL}/${fila.id}`), apiJson(`/api/licitaciones/${fila.id}`),
    ]);
    if (turno !== secuencia.current) return;
    setDetalle({
      ...(resultado.status === "fulfilled" ? resultado.value : { evaluacion: null, criterios: [], documentos: [], errorResultado: resultado.reason.message }),
      licitacion: ficha.status === "fulfilled" ? ficha.value.licitacion : fila,
      items: ficha.status === "fulfilled" ? ficha.value.items : [],
      errorFicha: ficha.status === "rejected" ? ficha.reason.message : "",
    });
  }
  function cerrarResultado() { secuencia.current++; setSeleccion(null); setDetalle(null); setErrorRevision(""); }
  async function evaluar() {
    let huboCambios = false;
    setOcupado("Comprobando licitaciones nuevas o modificadas…"); setError("");
    try {
      const { ids, total } = await apiJson(URL + "/plan");
      for (let i = 0; i < ids.length; i += 100) {
        setOcupado(`Filtrando ${Math.min(i + 100, ids.length)} de ${ids.length}…`);
        await apiJson(URL + "/evaluar", { method: "POST", body: { ids: ids.slice(i, i + 100) } });
        huboCambios = true;
      }
      setResumen(ids.length ? `${ids.length} licitaciones filtradas automáticamente con la ficha y sus ítems.` : `${total} licitaciones al día. No hay cambios por evaluar.`);
      if (huboCambios) { setSeleccion(null); setDetalle(null); }
    } catch (e) { setError(e.message); }
    finally {
      if (huboCambios) { actualizar(); await onActualizada?.(); }
      setOcupado("");
    }
  }
  async function revisar(accion, motivoAnalisis) {
    setOcupado("Guardando revisión…"); setErrorRevision("");
    try {
      await apiJson(`${URL}/${seleccion.id}/revision`, { method: "POST", body: { evaluacion_id: detalle.evaluacion.id, accion, categoria_motivo: "otro", motivo: motivoAnalisis || "Decisión registrada por el usuario." } });
      setSeleccion(null); setDetalle(null); actualizar();
      await onActualizada?.();
    } catch (e) { setErrorRevision(e.message); }
    finally { setOcupado(""); }
  }
  const mensajeVacio = busquedaId.trim()
    ? `No hay licitaciones para el ID «${busquedaId.trim()}» con los filtros seleccionados.`
    : !datos.ids_fuente.length ? "Todavía no hay licitaciones vigentes para evaluar."
    : filtro === "preseleccionada"
      ? `No hay posibles oportunidades ${mostrarFechas ? "para estas fechas" : "en esta carga"}. Puedes consultar Revisión necesaria o Todas.`
      : `No hay resultados en esta vista${mostrarFechas ? " y rango de fechas" : ""}.`;
  return <section className="card panel preseleccion" aria-labelledby={`${id}-titulo`}>
    <div className="section-title pre-heading"><div className="pre-heading-title"><span className="pre-heading-icon"><Icon name="briefcase" /></span><div><h2 id={`${id}-titulo`}>{mostrarModalidades ? "Oportunidades para el hotel" : "Licitaciones para el hotel"}</h2><p className="sub">Considera salones para eventos y servicios de alimentación asociados. Se evalúan vigencia, ubicación en la RM y pertinencia.</p></div></div>
      {modalidad === "licitaciones"
        ? <button className="primary" disabled={!!ocupado || cargando} onClick={evaluar}>Actualizar preselección</button>
        : <button className="primary" type="button" disabled={actualizandoCompras} onClick={actualizarCompras}>{actualizandoCompras ? "Actualizando…" : "Actualizar preselección"}</button>}</div>
    {mostrarModalidades && <div className="pre-modalidades" role="tablist" aria-label="Tipo de oportunidades">{modalidades.map((m, i) => <button
      key={m.id} id={`${id}-tab-${m.id}`} type="button" role="tab" aria-selected={modalidad === m.id}
      aria-controls={`${id}-panel-${m.id}`} tabIndex={modalidad === m.id ? 0 : -1}
      onClick={() => elegirModalidad(m.id)} onKeyDown={e => moverModalidad(e, i)}>
      <Icon name={m.icono} />{m.nombre}</button>)}</div>}
    <PilaresPreseleccion />
    <div className="pre-modalidad-panel" id={`${id}-panel-licitaciones`} role={mostrarModalidades ? "tabpanel" : undefined}
      aria-labelledby={mostrarModalidades ? `${id}-tab-licitaciones` : undefined} hidden={modalidad !== "licitaciones"} tabIndex={mostrarModalidades ? 0 : undefined}>
    <UltimaBusqueda fuente="licitaciones" />
    <p className="pre-nota" role="note">Las licitaciones nuevas se evalúan durante la carga. “Actualizar preselección” reintenta las pendientes. La lista puede incluir procesos abiertos y cerrados; la etiqueta junto al código indica si todavía reciben ofertas.</p>
    <PreseleccionControles clasificacion={filtro} ordenCierre={ordenCierre} ordenPublicacion={ordenPublicacion}
      onOrdenCierre={valor => { setOrdenCierre(valor); setOffset(0); }} onOrdenPublicacion={valor => { setOrdenPublicacion(valor); setOffset(0); }}
      total={datos.total} disabled={!!ocupado} mostrarBusquedaId={mostrarInformacion}
      busquedaId={busquedaId} onBusquedaId={setBusquedaId}
      onClasificacion={valor => { setFiltro(valor); setOffset(0); }} />
    {filtro === "" && <p className="pre-nota" role="note">Vista de auditoría: incluye posibles oportunidades, revisiones y descartes. Este total no representa oportunidades para el hotel.</p>}
    {ocupado && <p role="status">{ocupado}</p>}
    {!ocupado && resumen && <p className="sub" role="status">{resumen}</p>}
    {(error || errorCarga) && <p className="msg err" role="alert">{error || errorCarga}</p>}
    {cargando ? <p role="status">Cargando preselección…</p> : <>
      {!datos.filas.length && !error && !errorCarga && !ocupado && <p className="pre-vacio">{mensajeVacio}</p>}
      <div className="pre-lista" role="region" aria-label="Resultados de licitaciones para el hotel" tabIndex={datos.filas.length ? 0 : undefined}>{datos.filas.map(fila => <article key={fila.id} className="pre-fila" data-estado={fila.estado_seleccion} data-cliente-importante={!!fila.clientes_importantes?.length && ["preseleccionada", "revision_manual"].includes(fila.estado_seleccion)}>
        <div className={mostrarInformacion ? "pre-fila-ampliada" : undefined}><div className="pre-fila-meta">
          <div className="pre-fila-identidad"><span className="sub">{fila.codigo_externo}</span><EstadoPlazo fila={fila} /></div>
          <CierrePlazo fechaCierre={fila.fecha_cierre} />
        </div>
          {["preseleccionada", "revision_manual"].includes(fila.estado_seleccion) && <ClienteImportanteBadge clientes={fila.clientes_importantes} />}
          <TituloLicitacion licitacion={fila} />
          {mostrarInformacion && <ResumenLicitacion licitacion={fila} />}
          {fila.estado_seleccion === "descartada" && <p className="pre-regla-aplicada"><strong>{fila.motivo_seleccion?.includes("Registrado por ") ? "Descartada por usuario" : `Descartada por regla${fila.pilar_decisivo ? ` · ${nombrePilar[fila.pilar_decisivo] || fila.pilar_decisivo}` : " aplicada"}`}:</strong> {fila.motivo_seleccion || "No se recibió el detalle del descarte."}</p>}
          {fila.estado_seleccion !== "descartada" && <p>{fila.motivo_seleccion}</p>}
          <span className={"badge " + (tonos[fila.estado_seleccion] || "")}>{fila.estado_seleccion === "descartada" && fila.motivo_seleccion?.includes("Registrado por ") ? "Descartada por usuario" : fila.estado_seleccion === "preseleccionada" && fila.motivo_seleccion?.startsWith("Candidato para el hotel:") ? "Posible oportunidad · sede por confirmar" : etiquetas[fila.estado_seleccion]}</span></div>
        <div className="pre-fila-acciones"><button disabled={!!ocupado} onClick={() => abrir(fila)}>Ver resultado</button>{fila.url_oficial && <a href={fila.url_oficial} target="_blank" rel="noreferrer">Mercado Público ↗</a>}</div>
      </article>)}</div>
      {datos.total > 0 && <PaginacionResultados total={datos.total} offset={offset} limite={25}
        cargando={cargando || !!ocupado} onCambiar={setOffset} etiqueta="Páginas de licitaciones" />}
    </>}
    <ResultadoPreseleccion fila={seleccion} detalle={detalle} pilares={pilares} etiquetas={etiquetas} tonos={tonos}
      ocupado={ocupado} errorRevision={errorRevision}
      onCerrar={cerrarResultado} onReintentar={() => abrir(seleccion)} onRevisar={revisar} />
    </div>
    {mostrarModalidades && <div className="pre-modalidad-panel" id={`${id}-panel-compras-agiles`} role="tabpanel"
      aria-labelledby={`${id}-tab-compras-agiles`} hidden={modalidad !== "compras-agiles"} tabIndex={0}>
      {comprasVisitadas && <PanelComprasAgiles ref={comprasRef} version={versionComprasAgiles} integrado />}
    </div>}
  </section>;
}
