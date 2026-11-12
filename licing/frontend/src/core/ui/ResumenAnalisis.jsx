import { useCallback, useEffect, useState } from "react";
import { apiJson } from "../api/client";
import "./resumen-analisis.css";

const NOMBRES_CRITERIO = {
  vigencia: "Vigencia",
  ubicacion: "Lugar de prestación",
  pertinencia: "Compatibilidad con el hotel",
  servicio: "Servicio solicitado",
};
const ESTADO_CRITERIO = {
  cumple: "Confirmado",
  no_cumple: "No compatible",
  sin_informacion: "Por confirmar",
  por_verificar: "Por confirmar",
};

function clean(value, max = 180) {
  if (typeof value !== "string") return "";
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

export default function ResumenAnalisis({
  estado,
  motivo,
  criterios = [],
  fechaCierre,
  monto,
  lugar,
  entidadTipo,
  entidadId,
  resumenIA,
  clasificacionActual,
  hashFuente,
  fuenteActualizada = false,
  onDecidir,
  onActualizarEvaluacion,
  prepararResumenIA,
}) {
  const [ia, setIa] = useState(resumenIA || null);
  const [cargandoIa, setCargandoIa] = useState(false);
  const [errorIa, setErrorIa] = useState("");
  const [estadoErrorIa, setEstadoErrorIa] = useState(null);
  useEffect(() => { setIa(resumenIA || null); setErrorIa(""); setEstadoErrorIa(null); },
    [resumenIA, entidadId, fuenteActualizada, clasificacionActual]);
  const datos = [
    ["Cierre de ofertas", fechaCierre && fechaCierre !== "-" ? fechaCierre : ""],
    ["Monto informado", monto && monto !== "-" ? monto : "No informado"],
    ["Dirección informada en ficha", lugar],
    ...(ia ? [
      ["Lugar del evento", ia.ubicacion_requerida],
      ["Personas", ia.personas],
      ["Fechas y horarios", ia.fechas_horarios],
    ] : []),
  ].filter(([, value]) => value).map(([label, value]) => ({ label, value: clean(value, 140) }));
  const hallazgos = criterios
    .filter(c => c?.motivo || c?.resultado)
    .map(c => ({
      key: c.codigo || c.nombre,
      titulo: NOMBRES_CRITERIO[c.codigo] || c.nombre || c.codigo,
      estado: ESTADO_CRITERIO[c.resultado] || "Revisar",
      resultado: c.resultado || "sin_informacion",
      motivo: clean(c.motivo, 190),
    }));

  const claseIA = clasificacionActual || estado;
  const nombreProceso = entidadTipo === "compra_agil" ? "Compra Ágil" : "licitación";
  const claseAptaIA = ["preseleccionada", "posible_oportunidad", "revision_manual", "revision_necesaria"].includes(claseIA);
  const puedeUsarIa = entidadTipo && entidadId && claseAptaIA && fuenteActualizada;
  const cargarLecturaIa = useCallback(async () => {
    setCargandoIa(true);
    setErrorIa("");
    setEstadoErrorIa(null);
    try {
      let fuenteActual = entidadTipo === "compra_agil" && prepararResumenIA
        ? await prepararResumenIA()
        : { hashFuente, clasificacion: claseIA };
      const path = entidadTipo === "compra_agil"
        ? `/api/compras-agiles/${entidadId}/resumen-ia`
        : `/api/preseleccion/${entidadId}/resumen-ia`;
      const solicitarResumen = (hash, clasificacion) => apiJson(path, {
        method: "POST", body: { clasificacion, hash_fuente: hash },
      });
      let respuesta;
      try {
        respuesta = await solicitarResumen(fuenteActual.hashFuente, fuenteActual.clasificacion || claseIA);
      } catch (error) {
        // Si la ingesta coincidió con el clic, refresca y reintenta una sola vez.
        // La preparación de Compra Ágil consulta/reevalúa únicamente este ID.
        if (entidadTipo !== "compra_agil" || !prepararResumenIA || error.status !== 409) throw error;
        fuenteActual = await prepararResumenIA();
        respuesta = await solicitarResumen(fuenteActual.hashFuente, fuenteActual.clasificacion || claseIA);
      }
      setIa(respuesta.resumen);
    } catch (error) {
      setErrorIa(error.message || "No se pudo generar la lectura asistida.");
      setEstadoErrorIa(error.status || null);
    } finally {
      setCargandoIa(false);
    }
  }, [entidadTipo, entidadId, claseIA, hashFuente, prepararResumenIA]);
  async function actualizarEvaluacion() {
    if (!onActualizarEvaluacion) return cargarLecturaIa();
    setCargandoIa(true);
    setErrorIa(""); setEstadoErrorIa(null);
    try { await onActualizarEvaluacion(); }
    catch (error) { setErrorIa(error.message || "No se pudo actualizar la evaluación."); setEstadoErrorIa(error.status || null); }
    finally { setCargandoIa(false); }
  }
  const conflictoEvaluacion = estadoErrorIa === 409;
  const analisisEnCurso = estadoErrorIa === 423;
  const estadoLectura = ia ? "Análisis guardado" : analisisEnCurso ? "Análisis en preparación" : conflictoEvaluacion ? "Evaluación desactualizada" : errorIa ? "Gemini temporalmente no disponible" : puedeUsarIa ? "Análisis con IA opcional" : "Hallazgos del filtro";

  return <section className={`resumen-analisis resumen-analisis--${estado || "pendiente"}`} aria-label="Lectura de LICING">
    <header className="resumen-analisis__header">
      <span className="resumen-analisis__icono" aria-hidden="true">✓</span>
      <div><p>LECTURA DE LICING</p><h3>Resumen para decidir</h3></div>
      <small>{estadoLectura}</small>
    </header>
    {ia?.sintesis && <div className="resumen-analisis__sintesis"><span>Qué solicita {entidadTipo === "compra_agil" ? "esta Compra Ágil" : "esta licitación"}</span><p>{ia.sintesis}</p></div>}
    {datos.length > 0 && <dl className="resumen-analisis__datos">{datos.map(d => <div key={d.label}><dt>{d.label}</dt><dd>{d.value}</dd></div>)}</dl>}
    {motivo && !(errorIa && hallazgos.length) && <div className="resumen-analisis__conclusion"><strong>Por qué LICING la clasificó así</strong><p>{clean(motivo, 300)}</p></div>}
    {!!ia?.alertas?.length && <div className="resumen-analisis__ia-alertas"><strong>Alertas de la ficha</strong><ul>{ia.alertas.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
    {ia?.siguiente_paso && <div className="resumen-analisis__accion"><strong>Siguiente paso</strong><p>{ia.siguiente_paso}</p></div>}
    {onDecidir && puedeUsarIa && <div className="resumen-analisis__decisiones" aria-label="Registrar decisión">
      <span>¿Qué hacemos con esta licitación?</span>
      <div>
        <button type="button" className="is-discard" disabled={cargandoIa} onClick={() => onDecidir("descartar", ia?.siguiente_paso || motivo || "Descartada según el análisis de LICING.")}>Descartar</button>
        <button type="button" className="is-confirm" disabled={cargandoIa} onClick={() => onDecidir("confirmar_relevante", motivo || "Confirmada como posible oportunidad por el usuario.")}>Confirmar oportunidad</button>
        <button type="button" disabled={cargandoIa} onClick={() => onDecidir("mantener_pendiente", motivo || "Se mantiene en revisión por el usuario.")}>Mantener en revisión</button>
      </div>
    </div>}
    {!ia && !cargandoIa && hallazgos.length > 0 && <div className="resumen-analisis__hallazgos">
      <div className="resumen-analisis__hallazgos-heading">
        <div><span>LECTURA AUTOMÁTICA</span><strong>Hallazgos de LICING</strong></div>
        <small>{hallazgos.length} {hallazgos.length === 1 ? "criterio" : "criterios"}</small>
      </div>
      <ul>{hallazgos.map(h => <li className={`resultado-${h.resultado}`} key={h.key}>
        <span className="resumen-analisis__hallazgo-punto" aria-hidden="true" />
        <div><div className="resumen-analisis__hallazgo-titulo"><strong>{h.titulo}</strong><span>{h.estado}</span></div>
          {h.motivo && <p>{h.motivo}</p>}</div>
      </li>)}</ul>
    </div>}
    {puedeUsarIa && <div className={`resumen-analisis__ia-panel ${errorIa ? "has-error" : ""}`} aria-live="polite">
      {cargandoIa ? <>
        <span className="resumen-analisis__spinner resumen-analisis__spinner--large" aria-hidden="true" />
        <div className="resumen-analisis__ia-mensaje"><strong>Preparando resumen inteligente</strong>
          <p>LICING está organizando la información de la ficha y sus ítems. La evaluación del filtro sigue disponible mientras se prepara.</p>
          <div className="resumen-analisis__skeleton" aria-hidden="true"><i /><i /><i /></div>
        </div>
      </> : errorIa ? <>
        <span className="resumen-analisis__ia-fallback-icon" aria-hidden="true">i</span>
        <div className="resumen-analisis__ia-mensaje"><strong>{analisisEnCurso ? "El análisis ya se está preparando" : conflictoEvaluacion ? "La evaluación cambió antes de generar el resumen" : "Gemini no está disponible temporalmente"}</strong>
          <p>{analisisEnCurso ? errorIa : conflictoEvaluacion ? `${errorIa} Actualiza la evaluación de esta ${nombreProceso} y vuelve a iniciar el análisis.` : "Se muestran solo los hallazgos del filtro LICING basados en la ficha y sus ítems."}</p>
        </div>
        <button type="button" onClick={conflictoEvaluacion ? actualizarEvaluacion : cargarLecturaIa} disabled={cargandoIa}>
          {analisisEnCurso ? "Consultar análisis" : conflictoEvaluacion ? "Actualizar evaluación" : "Intentar de nuevo"}
        </button>
      </> : <div className="resumen-analisis__ia-inicio">
        <div className="resumen-analisis__ia-mensaje"><strong>{ia ? "Análisis guardado" : "¿Quieres un análisis asistido?"}</strong>
          <p>{ia ? "Puedes volver a solicitarlo; si la ficha no cambió, se reutilizará el resultado guardado." : `Gemini resumirá la ficha y sus ítems. El resultado se guardará para reutilizarlo al volver a abrir esta ${nombreProceso}.`}</p>
        </div>
        <button type="button" className="resumen-analisis__iniciar-ia" onClick={cargarLecturaIa} disabled={cargandoIa}>
          <span aria-hidden="true">✦</span> {ia ? "Consultar análisis guardado" : "Iniciar análisis con IA"}
        </button>
      </div>}
    </div>}
    {claseAptaIA && !fuenteActualizada && <div className="resumen-analisis__ia-panel has-error" role="status">
      <span className="resumen-analisis__ia-fallback-icon" aria-hidden="true">i</span>
      <div className="resumen-analisis__ia-mensaje"><strong>La evaluación necesita actualizarse</strong>
        <p>Los datos actuales de la ficha no coinciden con los usados por la última evaluación. Actualízala antes de pedir el análisis con IA.</p>
      </div>
      {onActualizarEvaluacion && <button type="button" onClick={actualizarEvaluacion} disabled={cargandoIa}>Actualizar evaluación</button>}
    </div>}
    {ia && <small className="resumen-analisis__nota">Datos extraídos de la ficha e ítems disponibles. Los campos ausentes no se consideran confirmados; la lectura no cambia la clasificación.</small>}
    {!ia && !cargandoIa && errorIa && <small className="resumen-analisis__nota">El resumen inteligente es opcional. La clasificación y los hallazgos del filtro permanecen disponibles.</small>}
  </section>;
}
