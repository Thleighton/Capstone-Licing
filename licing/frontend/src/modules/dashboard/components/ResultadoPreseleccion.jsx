import { useEffect, useId } from "react";
import Dialog from "../../../core/ui/Dialog";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import { dinero, fecha } from "../../../core/ui/format";
import "./resultado-preseleccion.css";

const resultados = { cumple: "Cumple", no_cumple: "No cumple", sin_informacion: "Por verificar" };
const tonosCriterio = { cumple: "green", no_cumple: "", sin_informacion: "amber" };
const estadoObservadoDocumento = { analizado: "Leído para el análisis", duplicado: "Mismo contenido que otro archivo", pendiente: "Detectado; pendiente de lectura", omitido_limite: "Detectado; no leído por límite de archivos", error: "No se pudo leer" };
const evidencia = c => (c.evidencias || []).filter(e => e.evidencia || e.texto).slice(0, 5);
const estadoDocumento = d => {
  if (d.estado_extraccion === "extraido") return "Texto extraído";
  const pendientes = d.cobertura?.paginas_pendientes;
  if (d.estado_extraccion === "parcial") return `Lectura parcial${pendientes?.length ? ` · páginas pendientes: ${pendientes.join(", ")}` : ""}`;
  if (d.estado_extraccion === "sin_texto") return "Sin texto seleccionable · requiere OCR o revisión manual";
  return d.incidencia?.mensaje || d.incidencia?.motivo || "Lectura pendiente de revisión";
};

export default function ResultadoPreseleccion({ fila, detalle, pilares, etiquetas, tonos, ocupado,
  motivo, categoria, errorRevision, onCerrar, onReintentar, onMotivo, onCategoria, onRevisar, onActualizarDocumentos }) {
  const id = useId();
  useEffect(() => {
    const estado = detalle?.ingesta_documental?.analisis_documental_estado;
    if (!fila || !["pendiente", "procesando"].includes(estado)) return undefined;
    const temporizador = setInterval(onActualizarDocumentos, 5000);
    return () => clearInterval(temporizador);
  }, [fila?.id, detalle?.ingesta_documental?.analisis_documental_estado, onActualizarDocumentos]);
  const licitacion = detalle?.licitacion || fila;
  const fichaMercadoPublico = licitacion?.url_oficial || fila?.url_oficial;
  const hallazgos = detalle?.ingesta_documental?.hallazgos_documentales?.length
    ? detalle.ingesta_documental.hallazgos_documentales
    : (detalle?.documentos || []).filter(d => d.hallazgos && Object.keys(d.hallazgos).length)
      .map(d => ({ documento: d.nombre, ...d.hallazgos }));
  const documentosTemporales = (detalle?.documentos || []).filter(d => d.temporal);
  const documentosObservados = detalle?.ingesta_documental?.documentos_observados || [];
  return <Dialog open={!!fila} onClose={onCerrar} onCancel={e => { if (ocupado) e.preventDefault(); }}
    className="pre-result-dialog" aria-labelledby={`${id}-titulo`}>
    {fila && <>
      <header className="pre-result-header">
        <div><p className="pre-result-kicker">Resultado de preselección · {fila.codigo_externo}</p>
          <TituloLicitacion as="h2" id={`${id}-titulo`} licitacion={{ ...fila, ...licitacion }} /></div>
        <button type="button" disabled={!!ocupado} onClick={onCerrar} autoFocus>Cerrar</button>
      </header>
      <div className="pre-result-body">
        <div className="pre-result-status">
          <span className={"badge " + (tonos[fila.estado_seleccion] || "")}>{etiquetas[fila.estado_seleccion] || "Sin evaluar"}</span>
          <ClienteImportanteBadge clientes={licitacion.clientes_importantes || fila.clientes_importantes} />
        </div>
        {fila.motivo_seleccion && <p className="pre-result-reason">{fila.motivo_seleccion}</p>}
        {(!!hallazgos.length || !!documentosTemporales.length) && <section className="pre-result-operativo" aria-label="Requisitos detectados en las bases">
          <div className="pre-result-operativo-titulo"><div><span className="pre-result-kicker">DETECTADO EN LAS BASES</span><h3>Condiciones para el evento</h3></div>
            {hallazgos.some(h => h.ubicacion?.fuera_zona_rm) && <span className="pre-result-alerta">Fuera de zona objetivo RM</span>}</div>
          {!hallazgos.length && <p className="pre-result-document-help">Se leyeron {documentosTemporales.length} archivo(s), pero no se detectaron automáticamente datos operativos en el texto extraído. Revisa los archivos y fragmentos más abajo.</p>}
          <div className="pre-result-operativo-grid">{hallazgos.map((h, i) => <article key={i}>
            <div><small>Lugar del evento</small><strong>{h.ubicacion?.resumen || "No identificado en lo leído"}</strong></div>
            <div><small>Asistentes</small><strong>{h.participantes?.resumen || "No identificados en lo leído"}</strong><span>Aforo máximo del hotel: por confirmar</span></div>
            <div><small>Fechas</small><strong>{h.fechas?.resumen || "No identificadas en lo leído"}</strong></div>
            <div><small>Duración</small><strong>{h.duracion?.resumen || "No identificada en lo leído"}</strong></div>
            <div><small>Horario</small><strong>{h.horario?.resumen || "No identificado en lo leído"}</strong></div>
            {!!h.servicios?.length && <div><small>Servicios</small><strong>{h.servicios.join(" · ")}</strong></div>}
            <div><small>Monto en documentos</small><strong>{h.presupuesto?.resumen || "No identificado en lo leído"}</strong></div>
            {h.ubicacion?.evidencia && <details><summary>Ver cita · página {h.ubicacion.evidencia.pagina}</summary><blockquote>{h.ubicacion.evidencia.texto}</blockquote></details>}
            {h.participantes?.evidencia && <details><summary>Cita de asistentes · página {h.participantes.evidencia.pagina}</summary><blockquote>{h.participantes.evidencia.texto}</blockquote></details>}
            {h.fechas?.evidencia && <details><summary>Cita de fechas · página {h.fechas.evidencia.pagina}</summary><blockquote>{h.fechas.evidencia.texto}</blockquote></details>}
            {h.horario?.evidencia && <details><summary>Cita de horario · página {h.horario.evidencia.pagina}</summary><blockquote>{h.horario.evidencia.texto}</blockquote></details>}
            {h.presupuesto?.evidencia && <details><summary>Cita del monto · página {h.presupuesto.evidencia.pagina}</summary><blockquote>{h.presupuesto.evidencia.texto}</blockquote></details>}
            {h.documento && <small className="pre-result-operativo-fuente">Fuente: {h.documento}</small>}
          </article>)}</div>
        </section>}
        {!detalle ? <p role="status">Cargando información de la licitación y su evaluación…</p> : <>
          {(detalle.errorResultado || detalle.errorFicha) && <div className="pre-result-error" role="alert">
            <p>{detalle.errorResultado ? "No se pudo cargar la evaluación. " + detalle.errorResultado : "No se pudo cargar la ficha completa. " + detalle.errorFicha}</p>
            <button type="button" onClick={onReintentar}>Reintentar</button>
          </div>}
          <section className="pre-result-section" aria-label="Información general">
            <h3>Información de la licitación</h3>
            <dl className="pre-result-facts">
              <div><dt>Organismo</dt><dd>{licitacion.nombre_organismo || "No informado"}</dd></div>
              <div><dt>Unidad compradora</dt><dd>{licitacion.nombre_unidad || "No informada"}</dd></div>
              <div><dt>Cierre de ofertas</dt><dd>{fecha(licitacion.fecha_cierre)}</dd></div>
              <div><dt>Publicación</dt><dd>{fecha(licitacion.fecha_publicacion)}</dd></div>
              <div><dt>Monto informado</dt><dd>{licitacion.monto_estimado == null ? "No informado" : dinero(licitacion.monto_estimado, licitacion.moneda)}</dd></div>
              <div><dt>Estado en Mercado Público</dt><dd>{licitacion.estado || "No informado"}</dd></div>
            </dl>
            {fichaMercadoPublico && <a className="pre-result-source" href={fichaMercadoPublico} target="_blank" rel="noreferrer">Abrir ficha oficial en Mercado Público ↗</a>}
          </section>
          {!!detalle.criterios?.length && <section className="pre-result-section" aria-label="Evaluación de los tres pilares">
            <h3>Resultado por pilar</h3>
            <div className="pre-result-pillars">{pilares.map((p, i) => {
              const c = detalle.criterios.find(c => c.codigo === p.codigo);
              if (!c) return null;
              const citas = evidencia(c);
              return <article className="pre-result-pillar" key={p.codigo}>
                <div className="pre-result-pillar-heading"><h4>{i + 1}. {p.nombre}</h4>
                  <span className={"badge " + (tonosCriterio[c.resultado] || "")}>{resultados[c.resultado] || c.resultado}</span></div>
                <p>{c.motivo || "Sin motivo informado."}</p>
                {!!citas.length && <details><summary>Ver evidencia ({citas.length})</summary>{citas.map((e, n) => {
                  const texto = e.evidencia || e.texto;
                  const match = String(e.fuente || "").match(/^documentos\[(.+)\]\.paginas\[(\d+)\]$/);
                  const doc = match && detalle.documentos?.find(d => String(d.id) === match[1]);
                  return <blockquote key={n}>{match && <small>{doc?.nombre || `Documento ${match[1]}`} · página {match[2]}</small>}<br />{texto}</blockquote>;
                })}</details>}
              </article>;
            })}</div>
          </section>}
          {licitacion.descripcion && <section className="pre-result-section"><h3>Descripción de la solicitud</h3><p className="pre-result-description">{licitacion.descripcion}</p></section>}
          {!!detalle.items?.length && <details className="pre-result-section pre-result-items" open={detalle.items.length <= 3}>
            <summary>Ítems solicitados ({detalle.items.length})</summary>
            {detalle.items.map((item, n) => <article key={item.id || n}>
              <h4>{item.nombre_producto || `Ítem ${n + 1}`}</h4>
              {item.descripcion && <p>{item.descripcion}</p>}
              <small>{item.codigo_producto && `Código: ${item.codigo_producto} · `}Cantidad: {item.cantidad ?? "No informada"} {item.unidad_medida || ""}</small>
            </article>)}
          </details>}
          <section className="pre-result-section" aria-label="Documentos de la licitación"><h3>Bases y anexos{detalle.documentos?.length ? ` · ${detalle.documentos.length} archivo(s)` : ""}</h3>
            <p className="pre-result-document-help">LICING revisa automáticamente las bases y anexos de oportunidades posibles y casos que requieren confirmar datos. Los archivos se leen en memoria; solo se conservan fragmentos breves con vencimiento.</p>
            {detalle.ingesta_documental?.analisis_documental_estado === "pendiente" && <p role="status" className="pre-result-notice">Revisión documental en cola. La licitación sigue disponible y no se descarta mientras se consulta.</p>}
            {detalle.ingesta_documental?.analisis_documental_estado === "procesando" && <p role="status" className="pre-result-notice">Revisando bases y anexos publicados en Mercado Público…</p>}
            {detalle.ingesta_documental?.analisis_documental_estado === "sin_documentos" && <p className="pre-result-notice">Aún no hay bases ni anexos publicados en la ficha oficial.</p>}
            {detalle.ingesta_documental?.analisis_documental_estado === "completado" && !detalle.documentos?.length && <p role="alert" className="pre-result-notice">El análisis terminó, pero el backend no entregó archivos temporales para mostrar. Esto requiere revisar la respuesta del análisis.</p>}
            {detalle.ingesta_documental?.analisis_documental_estado === "captcha" && <p className="pre-result-notice">Mercado Público solicitó CAPTCHA. La lectura se detuvo sin resolverlo; la oportunidad no se descarta.</p>}
            {detalle.ingesta_documental?.analisis_documental_estado === "error_temporal" && <p className="pre-result-notice">No se pudo leer la ficha ahora. LICING reintentará más tarde; la licitación no se descarta por este error.</p>}
            {!!documentosObservados.length && <><h4>Archivos encontrados en Mercado Público ({documentosObservados.length})</h4><ul className="pre-result-documents">{documentosObservados.map((d, i) => <li key={`${d.nombre}-${i}`}><strong>{d.nombre || "Archivo sin nombre"}</strong><span>{estadoObservadoDocumento[d.estado] || d.estado}{d.error ? ` · ${d.error}` : ""}{d.tipo ? ` · ${d.tipo}` : ""}{d.tamano ? ` · ${d.tamano}` : ""}{d.fecha ? ` · ${d.fecha}` : ""}{d.descripcion ? ` · ${d.descripcion}` : ""}</span></li>)}</ul></>}
            {fichaMercadoPublico && <a className="pre-result-source" href={fichaMercadoPublico} target="_blank" rel="noreferrer">Abrir ficha oficial para ver bases y anexos ↗</a>}
            {!!detalle.documentos?.length && <ul className="pre-result-documents">{detalle.documentos.map(d => <li key={d.id}>
              {fichaMercadoPublico ? <a href={fichaMercadoPublico} target="_blank" rel="noreferrer">{d.nombre} · Abrir ficha oficial ↗</a> : <strong>{d.nombre}</strong>}
              <span>{estadoDocumento(d)}{d.paginas ? ` · ${d.paginas} páginas` : ""}</span>
              {!!d.temporal && !!d.paginas_texto?.length && <details className="pre-result-excerpts"><summary>Fragmentos analizados ({d.paginas_texto.length})</summary>
                {d.paginas_texto.map((p, i) => <blockquote key={i}><small>Página {p.pagina}</small><br />{p.texto}</blockquote>)}
              </details>}
              {!!d.hallazgos?.participantes?.evidencia && <details className="pre-result-excerpts"><summary>Participantes detectados · página {d.hallazgos.participantes.evidencia.pagina}</summary><blockquote>{d.hallazgos.participantes.evidencia.texto}</blockquote></details>}
            </li>)}</ul>}
            {!!detalle.incidencias_documentales?.length && <ul className="pre-result-documents">{detalle.incidencias_documentales.map((inc, n) => <li key={n}><span>{inc.mensaje || inc.motivo || inc.codigo || "Documento no disponible"}</span></li>)}</ul>}
          </section>
          {(!detalle.fuente_actualizada || !detalle.evaluacion) && <p className="pre-result-notice">La evaluación necesita actualizarse. Usa Actualizar preselección antes de registrar una revisión.</p>}
          {detalle.evaluacion && detalle.fuente_actualizada && <details className="pre-result-section"><summary>Corregir clasificación (opcional)</summary>
            <fieldset disabled={!!ocupado} className="pre-result-review"><legend>Corrección del resultado</legend>
              <label>Motivo<textarea value={motivo} maxLength={1500} onChange={e => onMotivo(e.target.value)} placeholder="Explica el motivo de la corrección." /></label>
              <label>Aspecto<select value={categoria} onChange={e => onCategoria(e.target.value)}>{["plazo", "ubicacion", "servicio", "otro"].map(v => <option value={v} key={v}>{v === "plazo" ? "vigencia" : v}</option>)}</select></label>
              {errorRevision && <p className="pre-result-error" role="alert">{errorRevision}</p>}
              {ocupado && <p role="status">{ocupado}</p>}
              <div className="pre-result-actions">
                <button type="button" onClick={() => onRevisar("confirmar_relevante")}>Confirmar posible oportunidad</button>
                <button type="button" onClick={() => onRevisar("mantener_pendiente")}>Mantener pendiente</button>
                <button type="button" onClick={() => onRevisar("descartar")}>Descartar con motivo</button>
              </div>
            </fieldset>
          </details>}
        </>}
      </div>
    </>}
  </Dialog>;
}
