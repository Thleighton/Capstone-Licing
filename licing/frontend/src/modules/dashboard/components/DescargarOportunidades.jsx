import { useState } from "react";
import { apiFetch } from "../../../core/api/client";

export default function DescargarOportunidades() {
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState("");
  async function descargar() {
    setDescargando(true); setError("");
    try {
      const respuesta = await apiFetch("/api/preseleccion/exportar.xlsx");
      const archivo = await respuesta.blob();
      const url = URL.createObjectURL(archivo);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = respuesta.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || "LICING-oportunidades.xlsx";
      document.body.appendChild(enlace);
      enlace.click(); enlace.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e.message || "No se pudo descargar el Excel."); }
    finally { setDescargando(false); }
  }
  return <section className="card dashboard-export" aria-label="Exportar licitaciones">
    <div><strong>Listado de licitaciones</strong><p className="sub">Excel con posibles oportunidades, pendientes de revisión y descartadas.</p></div>
    <button type="button" className="primary" disabled={descargando} onClick={descargar}>
      {descargando ? "Preparando Excel…" : "Descargar Excel"}
    </button>
    {descargando && <span role="status" className="sub">Preparando todas las licitaciones…</span>}
    {error && <p className="msg err" role="alert">{error}</p>}
  </section>;
}
