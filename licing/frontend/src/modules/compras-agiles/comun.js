// Textos y cálculos compartidos por la página, la ficha y el apartado del dashboard.
import { useCallback, useEffect, useState } from "react";
import { apiJson } from "../../core/api/client";

export const ETIQUETAS = {
  preseleccionada: "Posible oportunidad",
  revision_manual: "Revisión necesaria",
  descartada: "Descartada por regla",
  pendiente_evaluacion: "Sin evaluar",
};
export const TONOS = { preseleccionada: "green", revision_manual: "amber", descartada: "", pendiente_evaluacion: "violet" };
export const PILARES = [
  { codigo: "vigencia", nombre: "Vigencia" },
  { codigo: "ubicacion", nombre: "Lugar del servicio" },
  { codigo: "pertinencia", nombre: "Servicio solicitado" },
];

let actualizacionEnCurso;
async function renovarEvaluaciones(onAvance, pendientesIniciales = 0) {
  let resultado;
  let evaluadas = 0;
  let pendientes = pendientesIniciales;
  do {
    const control = new AbortController();
    const limite = setTimeout(() => control.abort(), 60000);
    try {
      resultado = await apiJson("/api/compras-agiles/preseleccion/evaluar", {
        method: "POST", signal: control.signal,
      });
    } catch (error) {
      if (control.signal.aborted) {
        throw new Error("La evaluación tardó más de un minuto en responder. Puedes reintentar; lo ya guardado se conserva.");
      }
      throw error;
    } finally { clearTimeout(limite); }
    const lote = resultado.evaluadas?.length || 0;
    evaluadas += lote;
    pendientes = resultado.pendientes ?? pendientes;
    onAvance({ evaluadas, pendientes });
    if (pendientes > 0 && (!lote || resultado.sin_guardar)) {
      throw new Error("El lote no pudo guardar todas las evaluaciones. Lo ya procesado se conserva; vuelve a intentarlo.");
    }
  } while (pendientes > 0);
  return resultado;
}
function actualizarEvaluaciones(onAvance, pendientesIniciales) {
  if (!actualizacionEnCurso) {
    actualizacionEnCurso = renovarEvaluaciones(onAvance, pendientesIniciales)
      .finally(() => { actualizacionEnCurso = null; });
  }
  return actualizacionEnCurso;
}

/** Evalúa automáticamente solo registros nuevos o con reglas/datos desactualizados. */
export function useActualizarComprasAgiles(version) {
  const [revision, setRevision] = useState(0);
  const [actualizando, setActualizando] = useState(false);
  const [pendientes, setPendientes] = useState(0);
  const [avance, setAvance] = useState({ evaluadas: 0, pendientes: 0 });
  const [filtroActivo, setFiltroActivo] = useState(null);
  const [errorActualizacion, setError] = useState("");
  const [solicitud, setSolicitud] = useState(0);
  const actualizar = useCallback(async (pendientesIniciales = 0) => {
    setActualizando(true); setError("");
    setAvance({ evaluadas: 0, pendientes: pendientesIniciales });
    try {
      await actualizarEvaluaciones(progreso => {
        setAvance(progreso);
        setRevision(r => r + 1);
      }, pendientesIniciales);
    } catch (e) { setError(e.message); }
    finally {
      setRevision(r => r + 1); setSolicitud(s => s + 1);
      setActualizando(false);
    }
  }, []);
  useEffect(() => {
    const control = new AbortController();
    apiJson("/api/compras-agiles/preseleccion/plan", { signal: control.signal })
      .then(r => {
        setPendientes(r.pendientes);
        setFiltroActivo({ version: r.version_filtro, perfil: r.nombre_perfil });
      })
      .catch(e => { if (!control.signal.aborted) setError(e.message); });
    return () => control.abort();
  }, [version, solicitud, actualizar]);
  return {
    versionDatos: `${version || ""}:${revision}`, actualizando, errorActualizacion,
    pendientes, avance, filtroActivo, actualizar: () => actualizar(pendientes),
  };
}

// Las Compras Ágiles cierran en pocos días: el aviso se muestra desde 24 horas antes.
export function plazo(fechaCierre, ahora = Date.now()) {
  if (!fechaCierre) return null;
  const restantes = new Date(fechaCierre).getTime() - ahora;
  if (restantes <= 0) return { texto: "Plazo vencido", nivel: "critical" };
  if (restantes > 86400000) return null;
  const horas = restantes / 3600000;
  const texto = horas < 1 ? `Quedan ${Math.max(1, Math.ceil(restantes / 60000))} min` : `${Math.ceil(horas) === 1 ? "Queda" : "Quedan"} ${Math.ceil(horas)} h`;
  return { texto, nivel: horas <= 6 ? "critical" : "warning" };
}

/** Indicadores de /api/compras-agiles/resumen; `version` fuerza una nueva consulta. */
export function useResumenComprasAgiles(version) {
  const [estado, setEstado] = useState({ resumen: null, error: "" });
  useEffect(() => {
    const control = new AbortController();
    apiJson("/api/compras-agiles/resumen", { signal: control.signal })
      .then(resumen => setEstado({ resumen, error: "" }))
      .catch(e => { if (!control.signal.aborted) setEstado(previo => ({ ...previo, error: e.message })); });
    return () => control.abort();
  }, [version]);
  return estado;
}
