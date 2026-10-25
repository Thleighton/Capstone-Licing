import { useEffect, useId, useState } from "react";
import { apiJson } from "../../../core/api/client";
import { useStore } from "../../../core/store/createStore";
import Dialog from "../../../core/ui/Dialog";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import { dinero, fecha } from "../../../core/ui/format";
import { cerrarCompraAgil, fichaCompraAgil } from "../store";
import { ETIQUETAS, PILARES, TONOS } from "../comun";
import "../../dashboard/components/resultado-preseleccion.css";

const RESULTADOS = { cumple: "Cumple", no_cumple: "No cumple", sin_informacion: "Por verificar" };
const TONOS_CRITERIO = { cumple: "green", no_cumple: "", sin_informacion: "amber" };
const evidencias = c => (c.evidencias || []).map(e => e.evidencia || e.texto).filter(Boolean).slice(0, 5);

export default function FichaCompraAgil() {
  const id = useStore(fichaCompraAgil, s => s.id);
  const [detalle, setDetalle] = useState(null);
  const [intento, setIntento] = useState(0);
  const tituloId = useId();
  useEffect(() => {
    if (!id) return;
    let vivo = true;
    setDetalle(null);
    Promise.allSettled([apiJson(`/api/compras-agiles/${id}`), apiJson(`/api/compras-agiles/${id}/preseleccion`)])
      .then(([ficha, preseleccion]) => vivo && setDetalle({
        id,
        compra: ficha.value?.compra_agil, items: ficha.value?.items || [],
        error: ficha.status === "rejected" ? ficha.reason.message : "",
        preseleccion: preseleccion.status === "fulfilled" ? preseleccion.value : null,
      }));
    return () => { vivo = false; };
  }, [id, intento]);
  const actual = detalle?.id === id ? detalle : null;
  const c = actual?.compra;
  const evaluacion = actual?.preseleccion?.evaluacion;
  const vigente = evaluacion && actual.preseleccion.fuente_actualizada;
  const estado = vigente ? evaluacion.clasificacion : "pendiente_evaluacion";
  return <Dialog open={Boolean(id)} onClose={cerrarCompraAgil} className="pre-result-dialog" aria-labelledby={tituloId}>
    {id && <>
      <header className="pre-result-header">
        <div><p className="pre-result-kicker">Compra Ágil · {c?.codigo_externo || "Cargando…"}</p>
          {c ? <TituloLicitacion as="h2" id={tituloId} licitacion={c} /> : <h2 id={tituloId}>Detalle de la Compra Ágil</h2>}</div>
        <button type="button" onClick={cerrarCompraAgil} autoFocus>Cerrar</button>
      </header>
      <div className="pre-result-body">
        {!actual ? <p role="status">Cargando la Compra Ágil y su preselección…</p> : actual.error ? <div className="pre-result-error" role="alert">
          <p>No se pudo cargar la Compra Ágil. {actual.error}</p><button type="button" onClick={() => setIntento(n => n + 1)}>Reintentar</button>
        </div> : <>
          <div className="pre-result-status">
            <span className={"badge " + (TONOS[estado] || "")}>{ETIQUETAS[estado]}</span>
            <ClienteImportanteBadge clientes={c.clientes_importantes} />
          </div>
          <p className="pre-result-reason">{vigente ? evaluacion.motivo : actual.preseleccion
            ? "La preselección se actualizará en el próximo turno de ingesta."
            : "No se pudo consultar la preselección. Los datos de la compra están disponibles."}</p>
          <section className="pre-result-section" aria-label="Información general">
            <h3>Información de la Compra Ágil</h3>
            <dl className="pre-result-facts">
              <div><dt>Organismo</dt><dd>{c.nombre_organismo || "No informado"}</dd></div>
              <div><dt>Unidad compradora</dt><dd>{c.nombre_unidad || "No informada"}</dd></div>
              <div><dt>Región del comprador</dt><dd>{c.region_comprador || "No informada"}</dd></div>
              <div><dt>Llamado</dt><dd>{c.estado_convocatoria === 2 ? "Segundo llamado" : c.estado_convocatoria === 1 ? "Primer llamado" : "No informado"}</dd></div>
              <div><dt>Publicación</dt><dd>{fecha(c.fecha_publicacion)}</dd></div>
              <div><dt>Cierre de cotizaciones</dt><dd>{fecha(c.fecha_cierre)}</dd></div>
              <div><dt>Presupuesto {c.tipo_presupuesto ? `(${c.tipo_presupuesto.toLowerCase()})` : ""}</dt>
                <dd>{c.monto_disponible == null ? "No informado" : dinero(c.monto_disponible, c.moneda)}</dd></div>
              <div><dt>Cotizaciones recibidas</dt><dd>{c.total_ofertas_recibidas ?? "No informado"}</dd></div>
              <div><dt>Dirección de entrega</dt><dd>{c.direccion_entrega || "No informada"}</dd></div>
              <div><dt>Plazo de entrega</dt><dd>{c.plazo_entrega_dias == null ? "No informado" : `${c.plazo_entrega_dias} días`}</dd></div>
            </dl>
            {c.url_oficial && <a className="pre-result-source" href={c.url_oficial} target="_blank" rel="noopener noreferrer">Abrir ficha oficial en Mercado Público ↗</a>}
          </section>
          {vigente && !!actual.preseleccion.criterios?.length && <section className="pre-result-section" aria-label="Evaluación de los tres pilares">
            <h3>Resultado por pilar</h3>
            <div className="pre-result-pillars">{PILARES.map((p, i) => {
              const criterio = actual.preseleccion.criterios.find(x => x.codigo === p.codigo);
              if (!criterio) return null;
              const citas = evidencias(criterio);
              return <article className="pre-result-pillar" key={p.codigo}>
                <div className="pre-result-pillar-heading"><h4>{i + 1}. {p.nombre}</h4>
                  <span className={"badge " + (TONOS_CRITERIO[criterio.resultado] || "")}>{RESULTADOS[criterio.resultado] || criterio.resultado}</span></div>
                <p>{criterio.motivo || "Sin motivo informado."}</p>
                {!!citas.length && <details><summary>Ver evidencia ({citas.length})</summary>{citas.map((texto, n) => <blockquote key={n}>{texto}</blockquote>)}</details>}
              </article>;
            })}</div>
          </section>}
          {c.descripcion && <section className="pre-result-section"><h3>Descripción de la solicitud</h3><p className="pre-result-description">{c.descripcion}</p></section>}
          {!!actual.items.length && <details className="pre-result-section pre-result-items" open={actual.items.length <= 3}>
            <summary>Productos solicitados ({actual.items.length})</summary>
            {actual.items.map(item => <article key={item.id}>
              <h4>{item.nombre_producto || `Producto ${item.posicion_fuente}`}</h4>
              {item.descripcion && item.descripcion !== c.descripcion && <p>{item.descripcion}</p>}
              <small>{item.codigo_producto && `Código: ${item.codigo_producto} · `}Cantidad: {item.cantidad ?? "No informada"} {item.unidad_medida || ""}</small>
            </article>)}
          </details>}
          {!!c.documentos?.length && <details className="pre-result-section"><summary>Adjuntos publicados ({c.documentos.length})</summary>
            {c.documentos.map(d => <p key={d.id}>{d.nombre || "Documento sin nombre"}</p>)}
            <p className="sub">Los adjuntos se descargan desde la ficha oficial en Mercado Público.</p>
          </details>}
          <p className="sub ca-nota-final">La preselección es una propuesta automática con los tres pilares. La decisión de cotizar corresponde al hotel.</p>
        </>}
      </div>
    </>}
  </Dialog>;
}
