import { useId } from "react";
import Dialog from "../../../core/ui/Dialog";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import { dinero, fecha } from "../../../core/ui/format";
import ResumenAnalisis from "../../../core/ui/ResumenAnalisis";
import "./resultado-preseleccion.css";

const resultados = { cumple: "Cumple", no_cumple: "No cumple", sin_informacion: "Por verificar" };
const tonosCriterio = { cumple: "green", no_cumple: "", sin_informacion: "amber" };
const evidencia = c => (c.evidencias || []).filter(e => e.evidencia || e.texto).slice(0, 5);

export default function ResultadoPreseleccion({ fila, detalle, pilares, etiquetas, tonos, ocupado,
  errorRevision, onCerrar, onReintentar, onRevisar }) {
  const id = useId();
  const licitacion = detalle?.licitacion || fila;
  const fichaMercadoPublico = licitacion?.url_oficial || fila?.url_oficial;
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
        {detalle && <ResumenAnalisis estado={fila.estado_seleccion} motivo={fila.motivo_seleccion}
          criterios={detalle.criterios || []}
          fechaCierre={fecha(licitacion.fecha_cierre)}
          monto={licitacion.monto_estimado == null ? "" : dinero(licitacion.monto_estimado, licitacion.moneda)}
          lugar={licitacion.direccion_entrega}
          entidadTipo="licitacion" entidadId={fila.id} resumenIA={detalle.resumen_ia?.resumen}
          clasificacionActual={detalle.evaluacion?.clasificacion} hashFuente={detalle.hash_fuente}
          fuenteActualizada={Boolean(detalle.fuente_actualizada)} onDecidir={onRevisar} />}
        {detalle?.revision_id && <p className="pre-result-notice">Decisión registrada{fila.revisado_por ? ` por ${fila.revisado_por}` : ""}{fila.revisado_en ? ` · ${fecha(fila.revisado_en)}` : ""}.</p>}
        {!detalle ? <p role="status">Cargando información de la licitación y su evaluación…</p> : <>
          {(detalle.errorResultado || detalle.errorFicha) && <div className="pre-result-error" role="alert">
            <p>{detalle.errorResultado ? "No se pudo cargar la evaluación. " + detalle.errorResultado : "No se pudo cargar la ficha completa. " + detalle.errorFicha}</p>
            <button type="button" onClick={onReintentar}>Reintentar</button>
          </div>}
          {(!detalle.fuente_actualizada || !detalle.evaluacion) && <p className="pre-result-notice">La evaluación necesita actualizarse. Usa Actualizar preselección antes de registrar una revisión.</p>}
          {errorRevision && <p className="pre-result-error" role="alert">{errorRevision}</p>}
          {ocupado && <p role="status">{ocupado}</p>}
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
          <section className="pre-result-section" aria-label="Bases y anexos"><h3>Bases y anexos</h3>
            <p className="pre-result-document-help">LICING no descarga ni procesa los anexos de Mercado Público. Puedes consultar las bases directamente en la ficha oficial.</p>
            {fichaMercadoPublico && <a className="pre-result-source" href={fichaMercadoPublico} target="_blank" rel="noreferrer">Abrir ficha oficial y consultar bases ↗</a>}
          </section>
        </>}
      </div>
    </>}
  </Dialog>;
}
