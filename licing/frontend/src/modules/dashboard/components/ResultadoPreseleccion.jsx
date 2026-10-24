import { useId } from "react";
import Dialog from "../../../core/ui/Dialog";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import { dinero, fecha } from "../../../core/ui/format";
import "./resultado-preseleccion.css";

const resultados = { cumple: "Cumple", no_cumple: "No cumple", sin_informacion: "Por verificar" };
const tonosCriterio = { cumple: "green", no_cumple: "", sin_informacion: "amber" };
const evidencia = c => (c.evidencias || []).map(e => e.evidencia || e.texto).filter(Boolean).slice(0, 5);

export default function ResultadoPreseleccion({ fila, detalle, pilares, etiquetas, tonos, ocupado,
  motivo, categoria, errorRevision, onCerrar, onReintentar, onMotivo, onCategoria, onRevisar }) {
  const id = useId();
  const licitacion = detalle?.licitacion || fila;
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
            {(licitacion.url_oficial || fila.url_oficial) && <a className="pre-result-source" href={licitacion.url_oficial || fila.url_oficial} target="_blank" rel="noreferrer">Abrir ficha oficial en Mercado Público ↗</a>}
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
                {!!citas.length && <details><summary>Ver evidencia ({citas.length})</summary>{citas.map((texto, n) => <blockquote key={n}>{texto}</blockquote>)}</details>}
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
          {!!detalle.documentos?.length && <details className="pre-result-section"><summary>Documentos complementarios ({detalle.documentos.length})</summary>
            {detalle.documentos.map(d => <p key={d.id}>{d.url_descarga ? <a href={d.url_descarga} target="_blank" rel="noreferrer">{d.nombre} ↗</a> : d.nombre}</p>)}
          </details>}
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
