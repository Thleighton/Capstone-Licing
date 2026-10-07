// Recomendaciones de DEMOSTRACIÓN (sin IA real). Cuando el motor IA/NLP esté listo,
// reemplazar DEMO_REQUESTS por las recomendaciones que entregue la API.
import { useState } from "react";
import { DEMO_REQUESTS, demoDate, demoRecommendation, seleccionDemo } from "../../../shared/demo/hotel";

const PRIORITIES = { high: "Alta prioridad", medium: "Prioridad media", low: "Baja prioridad" };
const ORDEN = ["high", "medium", "low"];

export default function AsistenteIA() {
  const [filtro, setFiltro] = useState("");
  const records = DEMO_REQUESTS.map(demoRecommendation)
    .sort((a, b) => ORDEN.indexOf(a.priority) - ORDEN.indexOf(b.priority))
    .filter(r => !filtro || r.priority === filtro);

  return (
    <section className="ai-home card panel" aria-labelledby="aiHomeTitle">
      <div className="section-title"><div><span className="hero-kicker">RECOMENDACIONES</span><h2 id="aiHomeTitle">Asistente IA</h2></div><span className="badge blue">Demo</span></div>
      <p className="section-help">Qué revisar primero, según disponibilidad y relación con el cliente.</p>
      <div className="ai-toolbar">
        <div className="priority-legend"><span className="priority high">● Alta</span><span className="priority medium">● Media</span><span className="priority low">● Baja</span></div>
        <label>Mostrar <select value={filtro} onChange={e => setFiltro(e.target.value)}>
          <option value="">Todas las prioridades</option><option value="high">Alta prioridad</option>
          <option value="medium">Prioridad media</option><option value="low">Baja prioridad</option>
        </select></label>
      </div>
      <div className="recommendation-grid" aria-live="polite" role="region" aria-label="Recomendaciones de ejemplo" tabIndex={0}>
        {records.length ? records.map(({ request: r, client, available, priority }) => (
          <article className={"recommendation " + priority} key={r.id}>
            <div className="rec-meta"><span className={"priority " + priority}>● {PRIORITIES[priority]}</span><span className="badge">{client.relation}</span></div>
            <h3>{r.name}</h3>
            <p className="sub">{client.name}</p>
            <p className="sub">{demoDate(r.date)} · {r.start}–{r.end} · {r.module} · {r.people} personas</p>
            <ul>
              <li>{available.length ? "Encaje preliminar: " + available.map(m => m.room.name).join(", ") + "." : "Sin salón compatible para el intervalo y los requisitos solicitados."}</li>
              <li>{client.known ? (available.length ? "Prioridad adicional por relación comercial previa." : "Cliente conocido; la relación previa no elimina el conflicto de disponibilidad.") : "Sin historial previo; revisar condiciones comerciales."}</li>
              <li>{available.length ? "Capacidad, montaje y equipos coinciden en el ejemplo. Servicios adicionales por confirmar." : "Revisar alternativas de fecha, montaje o capacidad."}</li>
            </ul>
            <a className="button" href="#disponibilidad" onClick={() => seleccionDemo.set({ requestId: r.id, date: r.date })}>Ver encaje y disponibilidad →</a>
          </article>
        )) : <p className="empty">Sin ejemplos para esta prioridad.</p>}
      </div>
      <p className="sub">Datos ficticios · sin IA real. Confirmar disponibilidad con el equipo.</p>
      <a href="#analisis">Revisar bases y documentos →</a>
    </section>
  );
}
