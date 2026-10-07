// Formulario del perfil del hotel. Hoy solo genera un resumen (no guarda).
// Siguiente paso (E2): guardar en criterio_busqueda vía POST /api/criterios.
import { useEffect, useRef, useState } from "react";
import { IMPORTANCE, INTAKE_GROUPS } from "./campos";
import { CAMPOS_VALIDADOS, validarPerfil } from "./sugerencias";
import AsistenteIntereses, { STATUS_INICIAL } from "./components/AsistenteIntereses";
import Campo from "./components/Campo";
import ResumenPerfil from "./components/ResumenPerfil";

const FUENTES_SUGERENCIA = ["servicios", "tipos_evento", "montaje", "exclusiones_busqueda"];

export default function PerfilHotelPage() {
  const formRef = useRef(null), resumenRef = useRef(null);
  const [resumen, setResumen] = useState(null); // FormData | null
  const [candidatos, setCandidatos] = useState([]);
  const [status, setStatus] = useState(STATUS_INICIAL);
  const [, forzar] = useState(0);

  const limpiarValidez = () => CAMPOS_VALIDADOS.forEach(n => formRef.current.elements[n].setCustomValidity(""));

  useEffect(() => {
    if (resumen) resumenRef.current?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
  }, [resumen]);

  function onInput(e) {
    limpiarValidez(); setResumen(null);
    if (FUENTES_SUGERENCIA.includes(e.target.name)) {
      setCandidatos([]);
      setStatus("Cambió la información de base. Vuelva a generar sugerencias y revise los términos ya incorporados.");
    } else if (["intereses_palabras", "intereses_frases"].includes(e.target.name)) forzar(n => n + 1);
  }

  function onSubmit(e) {
    e.preventDefault();
    const f = formRef.current, d = new FormData(f);
    limpiarValidez();
    const error = validarPerfil(d);
    if (error) { f.elements[error[0]].setCustomValidity(error[1]); f.elements[error[0]].reportValidity(); return; }
    setResumen(d);
  }

  function onReset() { setResumen(null); setCandidatos([]); setStatus(STATUS_INICIAL); limpiarValidez(); }

  return (
    <>
      <div className="intake-hero"><div><span className="hero-kicker">CONOZCAMOS TU HOTEL</span><h2>¿Qué hace que un evento calce con el hotel?</h2><p>La encargada de eventos define la oferta, las restricciones y los criterios para evaluar solicitudes de Mercado Público.</p></div><div className="hero-stamp"><strong>Oferta + requisitos</strong><span>+ disponibilidad real</span></div></div>
      <div className="notice"><strong>Prototipo para conversar con el cliente.</strong> Complete lo que conozca y deje pendiente lo que deba confirmarse. El resumen no guarda datos, reserva espacios ni determina compatibilidad automáticamente.</div>
      <form ref={formRef} id="criteriaForm" onSubmit={onSubmit} onReset={onReset} onInput={onInput}>
        <div className="form-layout">
          <div className="form-sections">
            {INTAKE_GROUPS.map(g => (
              <fieldset className="card panel" key={g.title}>
                <legend>{g.title}</legend>
                <p className="section-help">{g.help}</p>
                {g.matrix && (
                  <div className="criteria-matrix">{IMPORTANCE.map(([k, label]) => (
                    <label className="criteria-row" key={k}><span>{label}</span>
                      <select name={"importancia_" + k} defaultValue=""><option value="">Por definir</option><option>Obligatorio</option><option>Deseable / negociable</option><option>No relevante</option></select>
                    </label>))}
                  </div>
                )}
                <div className={"fields" + (g.matrix ? " spaced" : "")}>{g.fields.map(def => <Campo key={def[0]} def={def} />)}</div>
                {g.interests && (
                  <AsistenteIntereses formRef={formRef} candidatos={candidatos} setCandidatos={setCandidatos}
                    status={status} setStatus={setStatus} onCambio={() => { setResumen(null); forzar(n => n + 1); }} />
                )}
              </fieldset>
            ))}
          </div>
          <div className="form-summary card panel">
            <span className="badge blue">Ficha del cliente</span><h2>De la solicitud al encaje</h2>
            <ol><li><strong>Oferta:</strong> espacios, capacidades y servicios.</li><li><strong>Solicitud:</strong> evento, asistentes y horarios.</li><li><strong>Agenda:</strong> disponibilidad por confirmar.</li><li><strong>Decisión:</strong> criterios y revisión humana.</li></ol>
            <div className="summary-callout">Una coincidencia de palabras no confirma que el hotel pueda atender el evento.</div>
            <p className="sub">* Obligatorio para generar el resumen. El resto puede quedar por confirmar.</p>
            <button type="submit" className="primary">Ver resumen del perfil →</button>
            <button type="reset">Restablecer formulario</button>
            <p className="sub">Prototipo sin guardado. Al recargar se pierde lo completado.</p>
          </div>
        </div>
        {resumen && <ResumenPerfil ref={resumenRef} data={resumen} />}
      </form>
    </>
  );
}
