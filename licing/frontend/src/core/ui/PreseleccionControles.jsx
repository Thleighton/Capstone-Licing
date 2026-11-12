import "./preseleccion-controles.css";

export function PilaresPreseleccion() {
  return <>
    <ol className="oportunidad-pilares" aria-label="Pilares de preselección en orden">
      {["Vigencia", "Lugar del servicio", "Servicio solicitado"].map(nombre => <li key={nombre}><strong>{nombre}</strong></li>)}
    </ol>
    <p className="oportunidad-nota">Cumple los tres: posible oportunidad. Un incumplimiento confirmado: descartada. Si falta confirmar algún pilar: revisión necesaria. La decisión de postular corresponde al hotel.</p>
  </>;
}

export default function PreseleccionControles({ clasificacion, ordenCierre = "proximo", ordenPublicacion = "ninguna", onOrdenCierre, onOrdenPublicacion, onClasificacion, total, disabled = false, mostrarOrden = true, mostrarBusquedaId = false, busquedaId = "", onBusquedaId, entidad = "licitaciones", textoBusquedaId = "Ej. 599-40-LP26", ariaBusquedaId = "Buscar por ID de licitación" }) {
  return <div className="oportunidad-controles">
    {mostrarBusquedaId && <label>Buscar ID<input type="search" value={busquedaId} onChange={e => onBusquedaId?.(e.target.value)} placeholder={textoBusquedaId} aria-label={ariaBusquedaId} disabled={disabled} /></label>}
    {mostrarOrden && <>
    <label>Orden de cierre <select value={ordenCierre} onChange={e => onOrdenCierre?.(e.target.value)} disabled={disabled}>
      <option value="proximo">Más próximo</option><option value="lejano">Más lejano</option><option value="ninguno">Sin ordenar por cierre</option>
    </select></label>
    <label>Orden de publicación <select value={ordenPublicacion} onChange={e => onOrdenPublicacion?.(e.target.value)} disabled={disabled}>
      <option value="ninguna">Sin ordenar por publicación</option><option value="reciente">Más reciente</option><option value="antigua">Más antigua</option>
    </select></label>
    </>}
    <label>Mostrar <select value={clasificacion} onChange={e => onClasificacion(e.target.value)} disabled={disabled}>
      <option value="preseleccionada">Posible oportunidad</option>
      <option value="revision_manual">Revisión necesaria</option>
      <option value="descartada">Descartadas (por regla o usuario)</option>
      <option value="pendiente_evaluacion">Sin evaluar</option>
      <option value="">Todas (auditoría)</option>
    </select></label>
    <span className="sub" aria-live="polite">{total} {clasificacion === "" ? `${entidad} en auditoría` : total === 1 ? "resultado" : "resultados"}</span>
  </div>;
}
