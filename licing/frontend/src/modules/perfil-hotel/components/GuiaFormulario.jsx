// Botón "i" junto al título y diálogo con la guía de 3 pasos del formulario.
import { useRef, useState } from "react";
import { createStore, useStore } from "../../../core/store/createStore";
import Dialog from "../../../core/ui/Dialog";

const guia = createStore({ abierta: false });

export function BotonAyuda() {
  return (
    <button type="button" id="intakeInfo" className="info-button" aria-label="Cómo funcionará el formulario del perfil del hotel"
      aria-haspopup="dialog" title="Cómo funciona este formulario" onClick={() => guia.set({ abierta: true })}>i</button>
  );
}

const PASOS = [
  { tab: "1 · Oferta del hotel", body: <>
    <h3>La encargada define qué puede ofrecer el hotel</h3><p>Registra los salones del único edificio, capacidad por montaje, equipos, servicios y condiciones obligatorias o negociables.</p>
    <div className="help-example"><strong>Ejemplo ficticio · Salón A</strong><ul><li>Hasta 100 personas en montaje auditorio.</li><li>Proyector, audio y servicio de coffee break.</li><li>Disponibilidad: consultar la agenda del hotel por día y horario.</li></ul></div>
    <p>También puede escribir palabras y frases de interés o pedir sugerencias según la ficha: por ejemplo, “alojamiento” puede dar lugar a “hospedaje” y “pernoctación”. La encargada revisa, añade y edita los términos antes de utilizarlos.</p>
    <p className="sub">En el producto final se guardaría esta ficha en Licing y el LLM ayudaría a proponer términos. La disponibilidad requeriría una agenda actualizada por el equipo o una integración con el sistema de reservas.</p>
  </> },
  { tab: "2 · Solicitud", body: <>
    <h3>Mercado Público aporta lo que pide el cliente</h3><p>La licitación y sus bases aportarían los requisitos. El futuro LLM ayudaría a identificar y resumir los datos, dejando por confirmar lo que no esté claro.</p>
    <div className="help-example"><strong>Solicitud ficticia · Seminario</strong><ul><li>80 asistentes en montaje auditorio.</li><li>5 de octubre, de 14:00 a 18:00.</li><li>Proyector y coffee break; tiempo de montaje por confirmar.</li></ul></div>
    <p className="sub">Son datos de la solicitud, distintos del catálogo del hotel. El equipo podría revisar la ficha oficial y las bases para validarlos.</p>
  </> },
  { tab: "3 · Recomendación", body: <>
    <h3>El LLM recomendaría qué oportunidades revisar</h3><p>Licing contrastaría requisitos, capacidad, equipamiento, historial de clientes y disponibilidad. El LLM explicaría el interés de la oportunidad en el dashboard.</p>
    <div className="help-example"><span className="priority medium">● Prioridad media · ejemplo</span><p>“El Salón A tiene capacidad para 80 personas y ofrece los servicios solicitados. Falta confirmar la agenda y el tiempo de montaje.”</p></div>
    <p>La encargada verifica las bases y la agenda antes de decidir. Una recomendación no confirma una reserva ni garantiza una adjudicación.</p>
  </> },
];

export function GuiaFormulario() {
  const abierta = useStore(guia, s => s.abierta);
  const [paso, setPaso] = useState(0);
  const tabs = useRef([]);
  const ir = (n, foco = false) => {
    const p = Math.max(0, Math.min(2, n));
    setPaso(p);
    if (foco) setTimeout(() => tabs.current[p]?.focus(), 0);
  };
  const cerrar = () => { guia.set({ abierta: false }); setPaso(0); document.getElementById("intakeInfo")?.focus(); };
  const onKey = e => {
    const steps = { ArrowRight: (paso + 1) % 3, ArrowLeft: (paso + 2) % 3, Home: 0, End: 2 };
    if (Object.hasOwn(steps, e.key)) { e.preventDefault(); ir(steps[e.key], true); }
  };

  return (
    <Dialog open={abierta} onClose={cerrar} className="intake-help" aria-labelledby="intakeHelpTitle" aria-describedby="intakeHelpIntro">
      <div className="help-header"><div><span className="hero-kicker">GUÍA DEL FORMULARIO</span><h2 id="intakeHelpTitle">De los datos del hotel a una recomendación</h2></div>
        <button type="button" autoFocus onClick={cerrar}>Cerrar</button></div>
      <div className="help-content">
        <p id="intakeHelpIntro">Este formulario recoge lo que la encargada de eventos sabe del hotel. Así funcionaría en el producto final:</p>
        <div className="help-tabs" role="tablist" aria-label="Pasos del funcionamiento">
          {PASOS.map((p, i) => (
            <button key={i} type="button" id={"helpTab" + i} role="tab" aria-controls={"helpStep" + i} aria-selected={i === paso}
              tabIndex={i === paso ? 0 : -1} ref={el => (tabs.current[i] = el)} onClick={() => ir(i)} onKeyDown={onKey}>{p.tab}</button>
          ))}
        </div>
        {PASOS.map((p, i) => (
          <section key={i} id={"helpStep" + i} className="help-step" role="tabpanel" aria-labelledby={"helpTab" + i} tabIndex={0} hidden={i !== paso}>{p.body}</section>
        ))}
        <div className="notice"><strong>Estado actual:</strong> el formulario genera un resumen sin guardar datos. El LLM y la conexión con la agenda aún no están implementados. Todos los ejemplos de esta guía son ficticios.</div>
        <div className="help-controls">
          <button type="button" disabled={paso === 0} onClick={() => ir(paso - 1, true)}>Anterior</button>
          <span className="sub" role="status">Paso {paso + 1} de 3</span>
          <button type="button" className="primary" onClick={() => (paso === 2 ? cerrar() : ir(paso + 1, true))}>{paso === 2 ? "Entendido" : "Siguiente →"}</button>
        </div>
      </div>
    </Dialog>
  );
}
