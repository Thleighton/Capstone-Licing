// Cartera FICTICIA. Próximo paso: leer la tabla cliente_conocido desde la API.
import { DEMO_CLIENTS } from "../../shared/demo/hotel";

export default function ClientesPage() {
  return (
    <>
      <div className="notice"><strong>Cartera ficticia para validar el diseño.</strong> Ilustra organizaciones, contactos recurrentes e historial comercial. No contiene datos de clientes reales.</div>
      <div className="module-grid">
        <section className="card panel"><h2>Cómo se reconocería a un cliente</h2><p>La organización se contrastaría por RUT o identificador verificado; los contactos se vincularían a una ficha confirmada por el equipo.</p><p className="sub">La coincidencia de nombre por sí sola requiere revisión. No se asumiría una relación por un nombre similar.</p></section>
        <section className="card panel"><h2>Relación previa y prioridad</h2><p>Un cliente recurrente o un contacto conocido puede dar prioridad adicional a una oportunidad compatible.</p><p className="sub">La relación comercial no resuelve conflictos de horario, capacidad insuficiente ni falta de equipamiento.</p></section>
      </div>
      <div className="client-grid spaced">
        {DEMO_CLIENTS.map(c => (
          <article className="card panel client-card" key={c.id}>
            <span className="badge blue">{c.relation}</span>
            <h3 className="spaced">{c.name}</h3>
            <p>{c.visits} servicios anteriores · ejemplo</p>
            <div className="contact"><strong>Contacto</strong><br />{c.contact}</div>
            <ul className="history">{c.history.map(h => <li key={h}>{h}</li>)}</ul>
            <p className="sub">{c.note}</p>
            <span className={"priority " + (c.known ? "high" : "medium")}>{c.known ? "Puede aumentar prioridad si hay encaje" : "Prioridad según requisitos"}</span>
          </article>
        ))}
      </div>
    </>
  );
}
