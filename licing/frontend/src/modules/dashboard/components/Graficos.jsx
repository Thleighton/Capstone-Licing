const SIN_DATOS = <p className="empty">No se pudieron cargar los datos. Pulsa Actualizar para volver a intentar.</p>;
const CARGANDO = "Cargando indicadores…";
export function PublicacionesSemana({ datos, estado }) {
  if (estado !== "ok") return <div className="chart-placeholder">{estado === "err" ? SIN_DATOS : CARGANDO}</div>;
  const max = Math.max(1, ...datos.map(d => d.cantidad));
  const labels = datos.map(d => new Intl.DateTimeFormat("es-CL", { timeZone: "America/Santiago", day: "numeric", month: "short" }).format(new Date(d.fecha + "T12:00:00Z")));
  return <div className="chart-placeholder">
    <div className="bar-chart" role="img" aria-label={labels.map((d, i) => d + ": " + datos[i].cantidad + " publicaciones").join("; ")}>
      {datos.map((d, i) => <div className="bar-column" key={d.fecha}><b>{d.cantidad}</b><i style={{ height: Math.round(d.cantidad / max * 130) }} title={labels[i] + ": " + d.cantidad} /></div>)}
    </div><div className="chart-labels">{labels.map(d => <span key={d}>{d}</span>)}</div>
  </div>;
}
export function EstadoVigencia({ resumen, estado }) {
  if (estado !== "ok" || !resumen) return <div className="chart-placeholder">{estado === "err" ? SIN_DATOS : CARGANDO}</div>;
  const { total, abiertas } = resumen, otras = total - abiertas, pct = total ? abiertas / total * 100 : 0;
  return <div className="chart-placeholder"><div className="donut-layout">
    <div className="donut" role="img" aria-label={abiertas + " abiertas; " + otras + " en otro estado o con cierre vencido"}
      style={{ background: "conic-gradient(var(--accent) 0 " + pct + "%, var(--chart-muted, #e0e7f3) " + pct + "% 100%)" }}>
      <div className="donut-center"><strong>{total}</strong><span className="sub">guardadas</span></div>
    </div>
    <div><div className="legend-line"><i style={{ background: "var(--accent)" }} />Abiertas <b>{abiertas}</b></div>
      <div className="legend-line"><i style={{ background: "var(--chart-muted, #e0e7f3)" }} />Otras o vencidas <b>{otras}</b></div>
      <p className="sub">{total ? Math.round(pct) + "% abiertas según los datos guardados" : "Sin datos todavía"}</p></div>
  </div></div>;
}
