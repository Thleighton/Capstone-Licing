// Textos y cálculos compartidos por la página, la ficha y el apartado del dashboard.
import { useEffect, useState } from "react";
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
async function renovarEvaluaciones() {
  let resultado;
  do {
    resultado = await apiJson("/api/compras-agiles/preseleccion/evaluar", { method: "POST" });
  } while (resultado.pendientes > 0 && resultado.evaluadas?.length > 0 && !resultado.sin_guardar);
  return resultado;
}
function actualizarEvaluaciones() {
  if (!actualizacionEnCurso) {
    actualizacionEnCurso = renovarEvaluaciones()
      .finally(() => { actualizacionEnCurso = null; });
  }
  return actualizacionEnCurso;
}

/** Comprueba al entrar; guarda las evaluaciones desde Actualizar preselección. */
export function useActualizarComprasAgiles(version) {
  const [revision, setRevision] = useState(0);
  const [actualizando, setActualizando] = useState(false);
  const [pendientes, setPendientes] = useState(0);
  const [errorActualizacion, setError] = useState("");
  const [solicitud, setSolicitud] = useState(0);
  useEffect(() => {
    const control = new AbortController();
    apiJson("/api/compras-agiles/preseleccion/plan", { signal: control.signal })
      .then(r => setPendientes(r.pendientes))
      .catch(e => { if (!control.signal.aborted) setError(e.message); });
    return () => control.abort();
  }, [version, solicitud]);
  async function actualizar() {
    setActualizando(true); setError("");
    try {
      await actualizarEvaluaciones();
    } catch (e) { setError(e.message); }
    finally {
      setRevision(r => r + 1); setSolicitud(s => s + 1);
      setActualizando(false);
    }
  }
  return { versionDatos: `${version || ""}:${revision}`, actualizando, errorActualizacion, pendientes, actualizar };
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
