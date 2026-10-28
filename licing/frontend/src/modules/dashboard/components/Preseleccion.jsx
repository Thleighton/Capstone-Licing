import { useEffect, useId, useRef, useState } from "react";
import { apiJson } from "../../../core/api/client";
import Icon from "../../../core/ui/Icon";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import ResultadoPreseleccion from "./ResultadoPreseleccion";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import PanelComprasAgiles from "../../compras-agiles/components/PanelDashboard";
import PreseleccionControles, { PilaresPreseleccion } from "../../../core/ui/PreseleccionControles";
import "./preseleccion.css";

const URL = "/api/preseleccion";
const modalidades = [
  { id: "licitaciones", nombre: "Licitaciones", icono: "briefcase" },
  { id: "compras-agiles", nombre: "Compras Ágiles", icono: "bolt" },
];
const etiquetas = { preseleccionada: "Posible oportunidad", revision_manual: "Revisión necesaria", descartada: "Descartada por regla", pendiente_evaluacion: "Sin evaluar" };
const tonos = { preseleccionada: "green", revision_manual: "amber", descartada: "", pendiente_evaluacion: "violet" };
const pilares = [
  { codigo: "vigencia", nombre: "Vigencia" },
  { codigo: "ubicacion", nombre: "Lugar del servicio" },
  { codigo: "pertinencia", nombre: "Servicio solicitado" },
];
const fecha = valor => valor ? new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" }).format(new Date(valor)) : "Sin fecha";

export default function Preseleccion({ onActualizada, versionComprasAgiles, mostrarModalidades = false, q = "" }) {
  const id = useId();
  const [modalidad, setModalidad] = useState("licitaciones");
  const [comprasVisitadas, setComprasVisitadas] = useState(false);
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
  const [desde, setDesde] = useState(""), [hasta, setHasta] = useState("");
  const [version, setVersion] = useState(0); const [error, setError] = useState("");
  const [errorCarga, setErrorCarga] = useState("");
  const [cargando, setCargando] = useState(true); const [ocupado, setOcupado] = useState("");
  const [seleccion, setSeleccion] = useState(null); const [detalle, setDetalle] = useState(null);
  const [motivo, setMotivo] = useState(""); const [categoria, setCategoria] = useState("otro");
  const [errorRevision, setErrorRevision] = useState("");
  const [resumen, setResumen] = useState("");
  const secuencia = useRef(0);
  useEffect(() => {
    let vigente = true; setCargando(true);
    const control = new AbortController();
    const parametros = new URLSearchParams({ clasificacion: filtro, offset: String(offset), q });
    if (desde) parametros.set("cierre_desde", desde);
    if (hasta) parametros.set("cierre_hasta", hasta);
    const consulta = `${URL}?${parametros}`;
    apiJson(consulta, { signal: control.signal }).then(r => {
      if (vigente) { setDatos(r); setErrorCarga(""); }
    }).catch(e => { if (vigente) setErrorCarga(e.message); }).finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; control.abort(); };
  }, [filtro, offset, version, q, desde, hasta]);
  useEffect(() => { setOffset(0); }, [q]);
  useEffect(() => {
    let vigente = true;
    Promise.resolve().then(() => { if (vigente) evaluar(); });
    return () => { vigente = false; };
  }, []);
  const actualizar = () => setVersion(v => v + 1);
  async function abrir(fila) {
    const turno = ++secuencia.current;
    setSeleccion(fila); setDetalle(null); setMotivo(""); setCategoria("otro"); setErrorRevision("");
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
  async function revisar(accion) {
    if (motivo.trim().length < 5) { setErrorRevision("Escribe un motivo de al menos 5 caracteres."); return; }
    setOcupado("Guardando revisión…"); setErrorRevision("");
    try {
      await apiJson(`${URL}/${seleccion.id}/revision`, { method: "POST", body: { evaluacion_id: detalle.evaluacion.id, accion, categoria_motivo: categoria, motivo: motivo.trim() } });
      setSeleccion(null); setDetalle(null); actualizar();
      await onActualizada?.();
    } catch (e) { setErrorRevision(e.message); }
    finally { setOcupado(""); }
  }
  return <section className="card panel preseleccion" aria-labelledby={`${id}-titulo`}>
    <div className="section-title pre-heading"><div className="pre-heading-title"><span className="pre-heading-icon"><Icon name="briefcase" /></span><div><h2 id={`${id}-titulo`}>{mostrarModalidades ? "Oportunidades para el hotel" : "Licitaciones para el hotel"}</h2><p className="sub">Tres pilares: vigencia, ubicación en la RM y servicio solicitado.</p></div></div>
      {modalidad === "licitaciones"
        ? <button className="primary" disabled={!!ocupado || cargando} onClick={evaluar}>Actualizar preselección</button>
        : <a className="pre-mode-link" href="#compras-agiles">Ver todas las Compras Ágiles →</a>}</div>
    {mostrarModalidades && <div className="pre-modalidades" role="tablist" aria-label="Tipo de oportunidades">{modalidades.map((m, i) => <button
      key={m.id} id={`${id}-tab-${m.id}`} type="button" role="tab" aria-selected={modalidad === m.id}
      aria-controls={`${id}-panel-${m.id}`} tabIndex={modalidad === m.id ? 0 : -1}
      onClick={() => elegirModalidad(m.id)} onKeyDown={e => moverModalidad(e, i)}>
      <Icon name={m.icono} />{m.nombre}</button>)}</div>}
    <PilaresPreseleccion />
    <div className="pre-modalidad-panel" id={`${id}-panel-licitaciones`} role={mostrarModalidades ? "tabpanel" : undefined}
      aria-labelledby={mostrarModalidades ? `${id}-tab-licitaciones` : undefined} hidden={modalidad !== "licitaciones"} tabIndex={mostrarModalidades ? 0 : undefined}>
    <PreseleccionControles clasificacion={filtro} desde={desde} hasta={hasta} total={datos.total} disabled={!!ocupado}
      onClasificacion={valor => { setFiltro(valor); setOffset(0); }}
      onDesde={valor => { setDesde(valor); setOffset(0); }} onHasta={valor => { setHasta(valor); setOffset(0); }} />
    {ocupado && <p role="status">{ocupado}</p>}
    {!ocupado && resumen && <p className="sub" role="status">{resumen}</p>}
    {(error || errorCarga) && <p className="msg err" role="alert">{error || errorCarga}</p>}
    {cargando ? <p role="status">Cargando preselección…</p> : <>
      {!datos.filas.length && !error && !errorCarga && !ocupado && <p className="pre-vacio">{datos.ids_fuente.length ? filtro === "preseleccionada" ? "No hay posibles oportunidades para estas fechas. Puedes consultar Revisión necesaria o Todas." : "No hay resultados en esta vista y rango de fechas." : "Todavía no hay licitaciones vigentes para evaluar."}</p>}
      <div className="pre-lista" role="region" aria-label="Resultados de licitaciones para el hotel" tabIndex={datos.filas.length ? 0 : undefined}>{datos.filas.map(fila => <article key={fila.id} className="pre-fila" data-estado={fila.estado_seleccion} data-cliente-importante={!!fila.clientes_importantes?.length && ["preseleccionada", "revision_manual"].includes(fila.estado_seleccion)}>
        <div><span className="sub">{fila.codigo_externo} · Cierra {fecha(fila.fecha_cierre)}</span>
          {["preseleccionada", "revision_manual"].includes(fila.estado_seleccion) && <ClienteImportanteBadge clientes={fila.clientes_importantes} />}
          <TituloLicitacion licitacion={fila} /><p>{fila.motivo_seleccion}</p>
          <span className={"badge " + (tonos[fila.estado_seleccion] || "")}>{etiquetas[fila.estado_seleccion]}</span></div>
        <div className="pre-fila-acciones"><button disabled={!!ocupado} onClick={() => abrir(fila)}>Ver resultado</button>{fila.url_oficial && <a href={fila.url_oficial} target="_blank" rel="noreferrer">Mercado Público ↗</a>}</div>
      </article>)}</div>
      {datos.total > 25 && <nav className="pre-controles" aria-label="Páginas de licitaciones"><button disabled={offset === 0 || !!ocupado} onClick={() => setOffset(v => v - 25)}>Anterior</button>
        <span>{offset + 1}–{Math.min(offset + 25, datos.total)}</span><button disabled={offset + 25 >= datos.total || !!ocupado} onClick={() => setOffset(v => v + 25)}>Siguiente</button></nav>}
    </>}
    <ResultadoPreseleccion fila={seleccion} detalle={detalle} pilares={pilares} etiquetas={etiquetas} tonos={tonos}
      ocupado={ocupado} motivo={motivo} categoria={categoria} errorRevision={errorRevision}
      onCerrar={cerrarResultado} onReintentar={() => abrir(seleccion)} onMotivo={setMotivo} onCategoria={setCategoria} onRevisar={revisar} />
    </div>
    {mostrarModalidades && <div className="pre-modalidad-panel" id={`${id}-panel-compras-agiles`} role="tabpanel"
      aria-labelledby={`${id}-tab-compras-agiles`} hidden={modalidad !== "compras-agiles"} tabIndex={0}>
      {comprasVisitadas && <PanelComprasAgiles version={versionComprasAgiles} integrado />}
    </div>}
  </section>;
}
