// Embudo comercial de EJEMPLO. Próximo paso: estados reales por licitación (tabla de historial de estados).
import { useState } from "react";

const STAGES = ["Identificada", "Calificada", "Participada", "Adjudicada", "Descartada"];
const DEALS = [
  { name: "Delegación · alojamiento", amount: "$4.800.000", stage: 0 },
  { name: "Seminario · salón y catering", amount: "$2.600.000", stage: 1 },
  { name: "Jornada · coffee break", amount: "$950.000", stage: 2 },
  { name: "Encuentro institucional", amount: "$3.200.000", stage: 3 },
];

export default function SeguimientoPage() {
  const [deals, setDeals] = useState(DEALS);
  const avanzar = n => setDeals(ds => ds.map((d, i) => (i === n ? { ...d, stage: d.stage + 1 } : d)));

  return (
    <>
      <div className="notice"><strong>Tablero de ejemplo.</strong> Simula el avance comercial de una oportunidad. Los cambios se restablecen al recargar.</div>
      <div className="pipeline">
        {STAGES.map((s, i) => (
          <section className="stage" key={s}>
            <h2>{s}<span>{deals.filter(d => d.stage === i).length}</span></h2>
            {deals.map((d, n) => d.stage === i && (
              <article className="deal" key={n}>
                <span className="badge blue">Ejemplo {n + 1}</span><p>{d.name}</p><p className="sub">{d.amount}</p>
                {i < 3 ? <button onClick={() => avanzar(n)}>Avanzar a {STAGES[i + 1]}</button> : <span className="badge green">Resultado de ejemplo</span>}
              </article>
            ))}
            {!deals.some(d => d.stage === i) && <p className="sub">Sin oportunidades de ejemplo.</p>}
          </section>
        ))}
      </div>
      <section className="card panel spaced"><h2>Próximas acciones · ejemplo</h2>
        <div className="task-row"><span className="badge amber">Por coordinar</span><div><strong>Confirmar disponibilidad de salón</strong><p className="sub">Equipo de eventos · antes de preparar la oferta.</p></div></div>
        <div className="task-row"><span className="badge blue">Documentación</span><div><strong>Revisar antecedentes administrativos</strong><p className="sub">Responsable de licitaciones · antes de postular.</p></div></div>
      </section>
    </>
  );
}
