import { useEffect, useRef, useState } from "react";
import { apiJson } from "../../../core/api/client";
import "./preseleccion.css";

const URL = "/api/preseleccion";
const etiquetas = { preseleccionada: "Posible oportunidad", revision_manual: "Revisión necesaria", descartada: "Descartada por regla", pendiente_evaluacion: "Sin evaluar" };
const PENDIENTES = "pendientes_documentales";
const fecha = valor => valor ? new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" }).format(new Date(valor)) : "Sin fecha";
const evidencia = c => c.evidencias?.map(e => e.evidencia || e.texto).filter(Boolean).slice(0, 5) || [];
const base64 = file => new Promise((resolve, reject) => {
  const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]);
  reader.onerror = () => reject(new Error("No se pudo leer el archivo")); reader.readAsDataURL(file);
});

export default function Preseleccion() {
  const [datos, setDatos] = useState({ filas: [], total: 0, ids_fuente: [] });
  const [filtro, setFiltro] = useState(""); const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0); const [error, setError] = useState("");
  const [errorCarga, setErrorCarga] = useState("");
  const [cargando, setCargando] = useState(true); const [ocupado, setOcupado] = useState("");
  const [seleccion, setSeleccion] = useState(null); const [detalle, setDetalle] = useState(null);
  const [motivo, setMotivo] = useState(""); const [categoria, setCategoria] = useState("otro");
  const [tipo, setTipo] = useState("bases_tecnicas"); const [archivo, setArchivo] = useState(null);
  const archivoInput = useRef(null); const secuencia = useRef(0);
  useEffect(() => {
    let vigente = true; setCargando(true);
    const consulta = filtro === PENDIENTES ? `${URL}/pendientes-documentales?offset=${offset}` : `${URL}?clasificacion=${filtro}&offset=${offset}`;
    apiJson(consulta).then(r => {
      if (vigente) { setDatos(r); setErrorCarga(""); }
    }).catch(e => { if (vigente) setErrorCarga(e.message); }).finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [filtro, offset, version]);
  const actualizar = () => setVersion(v => v + 1);
  async function abrir(fila) {
    const turno = ++secuencia.current;
    setSeleccion(fila); setDetalle(null); setMotivo(""); setArchivo(null); setError("");
    try { const r = await apiJson(`${URL}/${fila.id}`); if (turno === secuencia.current) setDetalle(r); }
    catch (e) { if (turno === secuencia.current) setError(e.message); }
  }
  async function evaluar() {
    setOcupado("Preparando evaluación…"); setError("");
    try {
      const { ids_fuente: ids } = await apiJson(URL + "?limite=1");
      for (let i = 0; i < ids.length; i += 20) {
        setOcupado(`Evaluando ${Math.min(i + 20, ids.length)} de ${ids.length}…`);
        await apiJson(URL + "/evaluar", { method: "POST", body: { ids: ids.slice(i, i + 20) } });
      }
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
  async function subir(e) {
    e.preventDefault(); if (!archivo) return;
    if (archivo.size > 3 * 1024 * 1024) { setError("El PDF debe pesar como máximo 3 MB."); return; }
    setOcupado("Conservando PDF y leyendo sus páginas…"); setError("");
    try {
      await apiJson(`${URL}/${seleccion.id}/documentos`, { method: "POST", body: { nombre: archivo.name, tipo, contenido_base64: await base64(archivo) } });
      setArchivo(null); if (archivoInput.current) archivoInput.current.value = "";
      await abrir(seleccion); actualizar();
    } catch (e) { setError(e.message); }
    finally { setOcupado(""); }
  }
  async function retirar(id) {
    setOcupado("Retirando documento de la evaluación…"); setError("");
    try { await apiJson(`${URL}/${seleccion.id}/documentos/${id}`, { method: "DELETE" }); await abrir(seleccion); actualizar(); }
    catch (e) { setError(e.message); } finally { setOcupado(""); }
  }
  return <section className="card panel preseleccion" aria-labelledby="preseleccion-titulo">
    <div className="section-title"><div><h2 id="preseleccion-titulo">Oportunidades para el hotel</h2><p className="sub">Vigencia, servicios hoteleros y lugar de ejecución en la RM.</p></div>
      <button className="primary" disabled={!!ocupado || cargando} onClick={evaluar}>Actualizar preselección</button></div>
    <p className="pre-nota">Una coincidencia indica una posible oportunidad. Revisa sus bases, capacidad y disponibilidad antes de decidir postular. Los datos desconocidos quedan pendientes.</p>
    <div className="pre-controles"><label>Mostrar <select value={filtro} disabled={!!ocupado} onChange={e => { setFiltro(e.target.value); setOffset(0); }}>
      <option value="">Todas</option>{Object.entries(etiquetas).map(([k, v]) => <option key={k} value={k}>{v}</option>)}<option value={PENDIENTES}>Pendientes por revisar · documentos</option></select></label>
      <button disabled={!!ocupado} aria-pressed={filtro === PENDIENTES} onClick={() => { setFiltro(PENDIENTES); setOffset(0); }}>Pendientes por revisar</button>
      <span className="sub">{datos.total} resultados</span></div>
    {filtro === PENDIENTES && <p className="pre-nota">Licitaciones conservadas por problemas al descargar o leer sus documentos. Los motivos son orientativos y requieren revisión.</p>}
    {ocupado && <p role="status">{ocupado}</p>}
    {(error || errorCarga) && <p className="msg err" role="alert">{error || errorCarga}</p>}
    {cargando ? <p role="status">Cargando preselección…</p> : <>
      {!datos.filas.length && !error && !errorCarga && <p className="pre-vacio">{filtro === PENDIENTES ? "No hay incidencias documentales pendientes registradas." : datos.ids_fuente.length ? "No hay resultados en esta vista. Usa Actualizar preselección para evaluar los datos guardados." : "Todavía no hay licitaciones vigentes para evaluar."}</p>}
      <div className="pre-lista">{datos.filas.map(fila => <article key={fila.id} className="pre-fila">
        <div><span className="sub">{fila.codigo_externo} · Cierra {fecha(fila.fecha_cierre)}</span><h3>{fila.nombre}</h3><p>{fila.motivo_seleccion}</p>
          <span className="badge">{etiquetas[fila.estado_seleccion]}</span> {fila.cobertura === "sin_bases" && <span className="sub">Sin bases adjuntas</span>}</div>
        <div className="pre-fila-acciones"><button disabled={!!ocupado} onClick={() => abrir(fila)}>Revisar</button>{fila.url_oficial && <a href={fila.url_oficial} target="_blank" rel="noreferrer">Mercado Público ↗</a>}</div>
      </article>)}</div>
      {datos.total > 25 && <nav className="pre-controles" aria-label="Páginas de oportunidades"><button disabled={offset === 0 || !!ocupado} onClick={() => setOffset(v => v - 25)}>Anterior</button>
        <span>{offset + 1}–{Math.min(offset + 25, datos.total)}</span><button disabled={offset + 25 >= datos.total || !!ocupado} onClick={() => setOffset(v => v + 25)}>Siguiente</button></nav>}
    </>}
    {seleccion && <div className="pre-detalle" aria-label="Revisión de la licitación">
      <div className="section-title"><h3>{seleccion.codigo_externo} · {seleccion.nombre}</h3><button disabled={!!ocupado} onClick={() => { secuencia.current++; setSeleccion(null); }}>Cerrar revisión</button></div>
      {!detalle ? <p role="status">Cargando evidencia…</p> : <>
        {(!detalle.fuente_actualizada || !detalle.evaluacion) && <p className="msg">La evaluación necesita actualizarse. Usa Actualizar preselección antes de registrar una revisión.</p>}
        {!!detalle.incidencias_documentales?.length && <div className="msg" role="status"><strong>Pendiente de revisión documental</strong>
          {detalle.incidencias_documentales.map((i, n) => <p key={n}>{i.nombre && <strong>{i.nombre}: </strong>}{i.motivo}</p>)}</div>}
        {detalle.criterios.map(c => <div className="pre-criterio" key={c.id}><strong>{({ vigencia: "Vigencia", ubicacion: "Lugar del servicio", pertinencia: "Servicios del hotel", documentos: "Documentos" })[c.codigo] || c.nombre}</strong>
          <span className="badge">{({ cumple: "Coincidencia", no_cumple: "Fuera del criterio", sin_informacion: "Por verificar" })[c.resultado] || c.resultado}</span>
          {c.motivo && <p>{c.motivo}</p>}
          {evidencia(c).map((texto, i) => <blockquote key={i}>{texto}</blockquote>)}</div>)}
        {!!detalle.evaluacion?.metadatos?.requisitos_detectados?.hallazgos?.length && <details><summary>Cantidades, fechas y requisitos detectados · pendientes de interpretación</summary>
          {detalle.evaluacion.metadatos.requisitos_detectados.hallazgos.map((h, i) => <p key={i}><strong>{h.texto}</strong><br /><span className="sub">{h.fuente}</span><br />{h.contexto}</p>)}</details>}
        <h4>Bases y anexos</h4><p className="sub">PDF de hasta 3 MB y 120 páginas. Las páginas escaneadas o ilegibles requieren revisión; no se consideran información confirmada.</p>
        <p className="sub">{detalle.ingesta_documental?.estado === "descargada"
          ? "Documentos públicos obtenidos desde Mercado Público. Los archivos adjuntos protegidos no se descargan automáticamente."
          : ["procesando", "pendiente_continuar"].includes(detalle.ingesta_documental?.estado) ? "Descarga automática en curso."
          : detalle.ingesta_documental?.estado ? "No se completó la descarga automática. Se reintentará; puedes adjuntar las bases manualmente."
          : "Bases pendientes de descarga automática."}</p>
        {detalle.documentos.map(d => <div className="pre-documento" key={d.id}><div>{d.url_descarga ? <a href={d.url_descarga} target="_blank" rel="noreferrer">{d.nombre} ↗</a> : d.nombre}<br />
          <span className="sub">{({ extraido: "Texto leído", parcial: "Lectura parcial", sin_texto: "Requiere OCR o lectura manual", error: "No se pudo leer", pendiente: "Pendiente" })[d.estado_extraccion]} · {d.formato === "xlsx" ? `${d.paginas || "?"} hojas` : ["docx", "doc", "xls"].includes(d.formato) ? d.formato.toUpperCase() : `${d.paginas || "?"} páginas`}</span></div>
          {d.incidencia && <p>Motivo orientativo: {d.incidencia.motivo}</p>}
          <button disabled={!!ocupado} onClick={() => retirar(d.id)}>Retirar de la evaluación</button></div>)}
        <form onSubmit={subir} className="pre-carga"><label>Documento de {seleccion.codigo_externo}<input ref={archivoInput} type="file" accept="application/pdf,.pdf" disabled={!!ocupado} onChange={e => setArchivo(e.target.files?.[0] || null)} /></label>
          <label>Tipo <select value={tipo} disabled={!!ocupado} onChange={e => setTipo(e.target.value)}><option value="bases_tecnicas">Bases técnicas</option><option value="bases_administrativas">Bases administrativas</option><option value="anexo">Anexo</option><option value="otro">Otro</option></select></label>
          <button type="submit" disabled={!archivo || !!ocupado}>Adjuntar y reevaluar</button></form>
        {detalle.evaluacion && detalle.fuente_actualizada && <fieldset disabled={!!ocupado} className="pre-revision"><legend>Revisión manual</legend>
          <label>Motivo<textarea value={motivo} maxLength={1500} onChange={e => setMotivo(e.target.value)} placeholder="Explica por qué puede servir al hotel o por qué la descartas." /></label>
          <label>Aspecto <select value={categoria} onChange={e => setCategoria(e.target.value)}>{["servicio", "capacidad", "ubicacion", "plazo", "documentos", "presupuesto", "otro"].map(v => <option key={v}>{v}</option>)}</select></label>
          <div className="pre-controles"><button onClick={() => revisar("confirmar_relevante")}>Confirmar posible oportunidad</button><button onClick={() => revisar("mantener_pendiente")}>Mantener pendiente</button><button onClick={() => revisar("descartar")}>Descartar con motivo</button></div>
        </fieldset>}
      </>}
    </div>}
  </section>;
}
