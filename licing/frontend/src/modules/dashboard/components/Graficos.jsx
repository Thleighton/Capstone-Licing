import { esCandidata } from "../../../core/data/licitaciones";
import { DIA } from "../../../core/ui/format";

const SIN_DATOS = <p className="empty">No se pudieron cargar los datos. Pulsa Actualizar para volver a intentar.</p>;
const CARGANDO = "Cargando indicadores…";

export function PublicacionesSemana({ rows, estado }) {
  if (estado !== "ok") return <div className="chart-placeholder">{estado === "err" ? SIN_DATOS : CARGANDO}</div>;
  const dayKey = d => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Santiago", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
  const days = Array.from({ length: 7 }, (_, i) => new Date(Date.now() - (6 - i) * DIA));
  const values = days.map(d => rows.filter(r => r.fecha_publicacion && dayKey(new Date(r.fecha_publicacion)) === dayKey(d)).length);
  const max = Math.max(1, ...values);
  const labels = days.map(d => new Intl.DateTimeFormat("es-CL", { timeZone: "America/Santiago", day: "numeric", month: "short" }).format(d));
  return (
    <div className="chart-placeholder">
      <div className="bar-chart" role="img" aria-label={labels.map((d, i) => d + ": " + values[i] + " publicaciones").join("; ")}>
        {values.map((v, i) => <div className="bar-column" key={i}><b>{v}</b><i style={{ height: Math.round(v / max * 130) }} title={labels[i] + ": " + v} /></div>)}
      </div>
      <div className="chart-labels">{labels.map(d => <span key={d}>{d}</span>)}</div>
    </div>
  );
}

export function ResultadoPrefiltro({ rows, estado }) {
  if (estado !== "ok") return <div className="chart-placeholder">{estado === "err" ? SIN_DATOS : CARGANDO}</div>;
  const passed = rows.filter(esCandidata).length, rejected = rows.length - passed, pct = rows.length ? passed / rows.length * 100 : 0;
  return (
    <div className="chart-placeholder">
      <div className="donut-layout">
        <div className="donut" role="img" aria-label={passed + " pasan el filtro; " + rejected + " descartadas"}
          style={{ background: `conic-gradient(var(--accent) 0 ${pct}%, var(--chart-muted, #e0e7f3) ${pct}% 100%)` }}>
          <div className="donut-center"><strong>{rows.length}</strong><span className="sub">consultadas</span></div>
        </div>
        <div>
          <div className="legend-line"><i style={{ background: "var(--accent)" }} />Pasan el filtro <b>{passed}</b></div>
          <div className="legend-line"><i style={{ background: "var(--chart-muted, #e0e7f3)" }} />Descartadas <b>{rejected}</b></div>
          <p className="sub">{rows.length ? Math.round(pct) + "% de coincidencia inicial" : "Sin datos todavía"}</p>
        </div>
      </div>
    </div>
  );
}
