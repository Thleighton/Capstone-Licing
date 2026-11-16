import { useState } from "react";
import { apiFetch } from "../../../core/api/client";

export default function DescargarOportunidades({
  endpoint = "/api/preseleccion/exportar.xlsx",
  nombreFallback = "LICING-oportunidades.xlsx",
  entidad = "licitaciones",
}) {
  const [descargando, setDescargando] = useState(false);
  const [descargaLista, setDescargaLista] = useState(false);
  const [error, setError] = useState("");
  async function descargar() {
    setDescargando(true); setDescargaLista(false); setError("");
    try {
      const respuesta = await apiFetch(endpoint);
      const archivo = await respuesta.blob();
      const url = URL.createObjectURL(archivo);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = respuesta.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || nombreFallback;
      document.body.appendChild(enlace);
      enlace.click(); enlace.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setDescargaLista(true);
      setTimeout(() => setDescargaLista(false), 7000);
    } catch (e) { setError(e.message || "No se pudo descargar el Excel."); }
    finally { setDescargando(false); }
  }
  return <section className={`card dashboard-export${descargando ? " is-downloading" : ""}`}
    aria-label={`Exportar ${entidad}`} aria-busy={descargando}>
    <div><strong>Listado de {entidad}</strong><p className="sub">Excel con posibles oportunidades, pendientes de revisión y descartadas.</p></div>
    <button type="button" className="primary" disabled={descargando} onClick={descargar}>
      {descargando ? "Preparando Excel…" : "Descargar Excel"}
    </button>
    {descargando && <div className="export-state export-state-loading" role="status">
      <span className="export-spinner" aria-hidden="true" />
      <div><strong>Preparando el Excel de {entidad}</strong>
        <p>Reuniendo y ordenando los resultados. Esta descarga puede tardar un momento.</p>
        <span className="export-progress" aria-hidden="true"><span /></span>
      </div>
    </div>}
    {descargaLista && <div className="export-state export-state-ready" role="status">
      <span className="export-ready-icon" aria-hidden="true">✓</span>
      <div><strong>Excel listo</strong><p>La descarga de {entidad} se inició correctamente.</p></div>
    </div>}
    {error && <p className="msg err" role="alert">{error}</p>}
  </section>;
}
