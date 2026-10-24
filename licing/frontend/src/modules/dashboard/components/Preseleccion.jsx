import { useEffect, useRef, useState } from "react";
import { apiJson } from "../../../core/api/client";
import "./preseleccion.css";

const URL = "/api/preseleccion";
const etiquetas = { preseleccionada: "Posible oportunidad", revision_manual: "Revisión necesaria", descartada: "Descartada por regla", pendiente_evaluacion: "Sin evaluar" };
const fecha = valor => valor ? new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" }).format(new Date(valor)) : "Sin fecha";
const evidencia = c => c.evidencias?.map(e => e.evidencia || e.texto).filter(Boolean).slice(0, 5) || [];

export default function Preseleccion() {
  const [datos, setDatos] = useState({ filas: [], total: 0, ids_fuente: [] });
  const [filtro, setFiltro] = useState("preseleccionada"); const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0); const [error, setError] = useState("");
  const [errorCarga, setErrorCarga] = useState("");
  const [cargando, setCargando] = useState(true); const [ocupado, setOcupado] = useState("");
  const [seleccion, setSeleccion] = useState(null); const [detalle, setDetalle] = useState(null);
  const [motivo, setMotivo] = useState(""); const [categoria, setCategoria] = useState("otro");
  const [resumen, setResumen] = useState("");
  const secuencia = useRef(0);
  useEffect(() => {
    let vigente = true; setCargando(true);
    const consulta = `${URL}?clasificacion=${filtro}&offset=${offset}`;
    apiJson(consulta).then(r => {
      if (vigente) { setDatos(r); setErrorCarga(""); }
    }).catch(e => { if (vigente) setErrorCarga(e.message); }).finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [filtro, offset, version]);
  useEffect(() => {
    let vigente = true;
    Promise.resolve().then(() => { if (vigente) evaluar(); });
    return () => { vigente = false; };
  }, []);
  const actualizar = () => setVersion(v => v + 1);
  async function abrir(fila) {
    const turno = ++secuencia.current;
    setSeleccion(fila); setDetalle(null); setMotivo(""); setError("");
    try { const r = await apiJson(`${URL}/${fila.id}`); if (turno === secuencia.current) setDetalle(r); }
    catch (e) { if (turno === secuencia.current) setError(e.message); }
  }
  async function evaluar() {
    setOcupado("Comprobando licitaciones nuevas o modificadas…"); setError("");
    try {
      const { ids, total } = await apiJson(URL + "/plan");
      for (let i = 0; i < ids.length; i += 100) {
        setOcupado(`Filtrando ${Math.min(i + 100, ids.length)} de ${ids.length}…`);
        await apiJson(URL + "/evaluar", { method: "POST", body: { ids: ids.slice(i, i + 100) } });
      }
      setResumen(ids.length ? `${ids.length} licitaciones filtradas automáticamente con la ficha y sus ítems.` : `${total} licitaciones al día. No hay cambios por evaluar.`);
      setSeleccion(null); setDetalle(null);
    } catch (e) { setError(e.message); }
    finally { setOcupado(""); actualizar(); }
  }
  async function revisar(accion) {
    if (motivo.trim().length < 5) { setError("Escribe un motivo de al menos 5 caracteres."); return; }
    setOcupado("Guardando revisión…"); setError("");
    try {
      await apiJson(`${URL}/${seleccion.id}/revision`, { method: "POST", body: { evaluacion_id: detalle.evaluacion.id, accion, categoria_motivo: categoria, motivo: motivo.trim() } });
      setSeleccion(null); setDetalle(null); actualizar();
    } catch (e) { setError(e.message); }
    finally { setOcupado(""); }
  }
  return <section className="card panel preseleccion" aria-labelledby="preseleccion-titulo">
    <div className="section-title"><div><h2 id="preseleccion-titulo">Oportunidades para el hotel</h2><p className="sub">Vigencia, servicios hoteleros y lugar de ejecución en la RM.</p></div>
      <button className="primary" disabled={!!ocupado || cargando} onClick={evaluar}>Actualizar preselección</button></div>
    <p className="pre-nota">El filtro analiza automáticamente la ficha y los productos solicitados. No necesitas subir documentos. Las coincidencias son posibles oportunidades; la decisión de postular corresponde al hotel.</p>
    <div className="pre-controles"><label>Mostrar <select value={filtro} disabled={!!ocupado} onChange={e => { setFiltro(e.target.value); setOffset(0); }}>
      <option value="">Todas</option>{Object.entries(etiquetas).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <span className="sub">{datos.total} resultados</span></div>
    {ocupado && <p role="status">{ocupado}</p>}
    {!ocupado && resumen && <p className="sub" role="status">{resumen}</p>}
    {(error || errorCarga) && <p className="msg err" role="alert">{error || errorCarga}</p>}
    {cargando ? <p role="status">Cargando preselección…</p> : <>
      {!datos.filas.length && !error && !errorCarga && !ocupado && <p className="pre-vacio">{datos.ids_fuente.length ? filtro === "preseleccionada" ? "No se detectaron oportunidades para el hotel en esta carga. Puedes ver los motivos en Todas o Descartada por regla." : "No hay resultados en esta vista." : "Todavía no hay licitaciones vigentes para evaluar."}</p>}
      <div className="pre-lista">{datos.filas.map(fila => <article key={fila.id} className="pre-fila">
        <div><span className="sub">{fila.codigo_externo} · Cierra {fecha(fila.fecha_cierre)}</span><h3>{fila.nombre}</h3><p>{fila.motivo_seleccion}</p>
          <span className="badge">{etiquetas[fila.estado_seleccion]}</span></div>
        <div className="pre-fila-acciones"><button disabled={!!ocupado} onClick={() => abrir(fila)}>Ver resultado</button>{fila.url_oficial && <a href={fila.url_oficial} target="_blank" rel="noreferrer">Mercado Público ↗</a>}</div>
      </article>)}</div>
      {datos.total > 25 && <nav className="pre-controles" aria-label="Páginas de oportunidades"><button disabled={offset === 0 || !!ocupado} onClick={() => setOffset(v => v - 25)}>Anterior</button>
        <span>{offset + 1}–{Math.min(offset + 25, datos.total)}</span><button disabled={offset + 25 >= datos.total || !!ocupado} onClick={() => setOffset(v => v + 25)}>Siguiente</button></nav>}
    </>}
    {seleccion && <div className="pre-detalle" aria-label="Revisión de la licitación">
      <div className="section-title"><h3>{seleccion.codigo_externo} · {seleccion.nombre}</h3><button disabled={!!ocupado} onClick={() => { secuencia.current++; setSeleccion(null); }}>Cerrar revisión</button></div>
      {!detalle ? <p role="status">Cargando evidencia…</p> : <>
        {(!detalle.fuente_actualizada || !detalle.evaluacion) && <p className="msg">La evaluación necesita actualizarse. Usa Actualizar preselección antes de registrar una revisión.</p>}
        {detalle.criterios.filter(c => c.codigo !== "documentos").map(c => <div className="pre-criterio" key={c.id}><strong>{({ vigencia: "Vigencia", ubicacion: "Lugar del servicio", pertinencia: "Servicios del hotel" })[c.codigo] || c.nombre}</strong>
          <span className="badge">{({ cumple: "Coincidencia", no_cumple: "Fuera del criterio", sin_informacion: "Por verificar" })[c.resultado] || c.resultado}</span>
          {c.motivo && <p>{c.motivo}</p>}
          {evidencia(c).map((texto, i) => <blockquote key={i}>{texto}</blockquote>)}</div>)}
        {!!detalle.evaluacion?.metadatos?.requisitos_detectados?.hallazgos?.length && <details><summary>Cantidades, fechas y requisitos detectados · pendientes de interpretación</summary>
          {detalle.evaluacion.metadatos.requisitos_detectados.hallazgos.map((h, i) => <p key={i}><strong>{h.texto}</strong><br /><span className="sub">{h.fuente}</span><br />{h.contexto}</p>)}</details>}
        {!!detalle.documentos?.length && <details><summary>Documentos complementarios disponibles</summary>
          {detalle.documentos.map(d => <p key={d.id}>{d.url_descarga ? <a href={d.url_descarga} target="_blank" rel="noreferrer">{d.nombre} ↗</a> : d.nombre}</p>)}</details>}
        {detalle.evaluacion && detalle.fuente_actualizada && <details><summary>Corregir clasificación (opcional)</summary><fieldset disabled={!!ocupado} className="pre-revision"><legend>Corrección del resultado</legend>
          <label>Motivo<textarea value={motivo} maxLength={1500} onChange={e => setMotivo(e.target.value)} placeholder="Explica por qué puede servir al hotel o por qué la descartas." /></label>
          <label>Aspecto <select value={categoria} onChange={e => setCategoria(e.target.value)}>{["servicio", "capacidad", "ubicacion", "plazo", "documentos", "presupuesto", "otro"].map(v => <option key={v}>{v}</option>)}</select></label>
          <div className="pre-controles"><button onClick={() => revisar("confirmar_relevante")}>Confirmar posible oportunidad</button><button onClick={() => revisar("mantener_pendiente")}>Mantener pendiente</button><button onClick={() => revisar("descartar")}>Descartar con motivo</button></div>
        </fieldset></details>}
      </>}
    </div>}
  </section>;
}
