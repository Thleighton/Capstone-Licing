// Agenda de salones y comprobación de encaje — DATOS DE EJEMPLO (shared/demo/hotel.js).
// Próximo paso: leer tablas salon, salon_montaje y disponibilidad_salon desde la API.
import { useStore } from "../../core/store/createStore";
import { DEMO_HOTEL, DEMO_MODULES, DEMO_REQUESTS, DEMO_ROOMS, clockMinutes, demoDate, overlapping, roomMatch, seleccionDemo } from "../../shared/demo/hotel";

function AgendaSalones({ date }) {
  return DEMO_ROOMS.map(room => (
    <article className="card panel room-card" key={room.id}>
      <p className="room-location">{DEMO_HOTEL.name} · espacio interior</p>
      <h3>{room.name}</h3>
      <span className="badge blue">{room.capacity} personas · {room.layout}</span>
      <p className="room-features">{room.features}<br /><strong>Equipos:</strong> {room.equipment.join(", ")}</p>
      {DEMO_MODULES.map(([label, start, end]) => {
        const busy = room.bookings.filter(b => b.date === date && overlapping(clockMinutes(start), clockMinutes(end), b));
        return (
          <div className="slot" key={label}>
            <strong>{label} · {start}–{end}</strong>
            <span className={"priority " + (busy.length ? "low" : "high")}>{busy.length ? "No disponible en todo el módulo" : "Disponible en el ejemplo"}</span>
            {busy.length > 0 && <span>Reserva: {busy.map(b => b.start + "–" + b.end).join(", ")}</span>}
          </div>
        );
      })}
    </article>
  ));
}

function Encaje({ request }) {
  return (
    <div aria-live="polite">
      <p><strong>{demoDate(request.date)} · {request.start}–{request.end} · {request.module}</strong></p>
      <p className="sub">{request.people} asistentes · {request.layout} · {request.equipment.join(", ")} · Montaje: {request.setup} min antes / desmontaje: {request.teardown} min después.</p>
      {DEMO_ROOMS.map(room => {
        const m = roomMatch(room, request);
        return (
          <div className="match-row" key={room.id}>
            <div className="section-title"><strong>{room.name}</strong>
              <span className={"priority " + (m.compatible ? "high" : "low")}>{m.compatible ? "Compatible en el ejemplo" : "No compatible en el ejemplo"}</span></div>
            <p>{m.compatible ? "Capacidad, montaje, equipamiento y horario disponibles. Confirmar servicios adicionales y agenda con el equipo antes de reservar." : m.reasons.join(" ")}</p>
          </div>
        );
      })}
    </div>
  );
}

export default function DisponibilidadPage() {
  const { requestId, date } = useStore(seleccionDemo);
  const request = DEMO_REQUESTS.find(r => r.id === requestId) || DEMO_REQUESTS[0];

  return (
    <>
      <div className="notice"><strong>Un hotel, un edificio.</strong> Todos los salones pertenecen al Hotel Plaza San Francisco. Los nombres A, B y C, las capacidades, el equipamiento y las reservas son ejemplos pendientes de validar con la encargada de eventos.</div>
      <div className="section-title card panel">
        <div><h2>Agenda por día y módulo</h2><p className="sub">Mañana 09:00–13:00 · Tarde 14:00–18:00 · Jornada 09:00–18:00</p></div>
        <label className="agenda-date">Fecha de ejemplo
          <select value={date} onChange={e => seleccionDemo.set({ date: e.target.value })}>
            <option value="2026-10-05">5 de octubre de 2026</option><option value="2026-10-06">6 de octubre de 2026</option>
          </select></label>
      </div>
      <section className="hotel-building" aria-labelledby="buildingTitle">
        <div className="building-heading"><div><span className="hero-kicker">HOTEL → ESPACIOS INTERIORES</span><h2 id="buildingTitle">Hotel Plaza San Francisco</h2><p>Agenda de los salones del mismo edificio, por día, horario y módulo.</p></div><span className="badge blue">Edificio único · espacios de ejemplo</span></div>
        <div className="room-grid spaced"><AgendaSalones date={date} /></div>
        <p className="sub">La ocupación se consulta por salón: una reserva en un espacio no implica que todo el hotel esté ocupado. Distribución y recursos compartidos pendientes de confirmar con el hotel.</p>
      </section>
      <section className="card panel spaced">
        <div className="section-title"><h2>¿Qué salón podría atender la solicitud?</h2><span className="badge blue">Comprobación simulada</span></div>
        <p className="sub">Se compara la fecha y el intervalo completo, incluidos montaje y desmontaje, con las reservas del salón.</p>
        <label className="field">Solicitud de ejemplo
          <select value={request.id} onChange={e => { const r = DEMO_REQUESTS.find(x => x.id === e.target.value); seleccionDemo.set({ requestId: r.id, date: r.date }); }}>
            {DEMO_REQUESTS.map(r => <option key={r.id} value={r.id}>{r.name} · {demoDate(r.date)}</option>)}
          </select></label>
        <Encaje request={request} />
      </section>
    </>
  );
}
