import "./preseleccion-controles.css";

export function PilaresPreseleccion() {
  return <>
    <ol className="oportunidad-pilares" aria-label="Pilares de preselección en orden">
      {["Vigencia", "Lugar del servicio", "Servicio solicitado"].map(nombre => <li key={nombre}><strong>{nombre}</strong></li>)}
    </ol>
    <p className="oportunidad-nota">Cumple los tres: posible oportunidad. Un incumplimiento confirmado: descartada. Si falta confirmar algún pilar: revisión necesaria. La decisión de postular corresponde al hotel.</p>
  </>;
}

export default function PreseleccionControles({ clasificacion, desde, hasta, onClasificacion, onDesde, onHasta, total, disabled = false }) {
  return <div className="oportunidad-controles">
    <label>Mostrar <select value={clasificacion} onChange={e => onClasificacion(e.target.value)} disabled={disabled}>
      <option value="preseleccionada">Posible oportunidad</option>
      <option value="revision_manual">Revisión necesaria</option>
      <option value="">Todas</option>
    </select></label>
    <label>Cierre desde <input type="date" value={desde} max={hasta || undefined} onChange={e => onDesde(e.target.value)} disabled={disabled} /></label>
    <label>Hasta <input type="date" value={hasta} min={desde || undefined} onChange={e => onHasta(e.target.value)} disabled={disabled} /></label>
    <span className="sub" aria-live="polite">{total} {total === 1 ? "resultado" : "resultados"}</span>
  </div>;
}
