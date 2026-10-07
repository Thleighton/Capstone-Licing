import { useState } from "react";
import { EJEMPLOS, analizarEjemplo } from "./api";

function Resultado({ estado }) {
  if (!estado) return <><p className="empty">Selecciona un ejemplo y simula el análisis para explorar el resultado esperado.</p><div className="skeleton" /><div className="skeleton short" /></>;
  if (estado.cargando) return <><p className="empty">Analizando…</p><div className="skeleton" /><div className="skeleton short" /></>;
  if (estado.error) return <p className="msg err">No se pudo analizar: {estado.error}</p>;
  const r = estado.resultado;
  return (
    <>
      <p><span className="badge blue">{r.simulado ? "Resultado simulado" : "Resultado del análisis"}</span></p>
      <h3>{r.titulo}</h3>
      <dl className="kv">
        <dt>Servicio</dt><dd>{r.servicio}</dd>
        <dt>Participantes</dt><dd>{r.participantes}</dd>
        <dt>Presupuesto</dt><dd>{r.presupuesto}</dd>
        <dt>Documentos</dt><dd>{r.documentos}</dd>
      </dl>
      <div className="notice"><strong>Pendiente de validar:</strong> {r.pendientes}</div>
      <a className="button" href="#formulario">Revisar criterios →</a>
    </>
  );
}

export default function AnalisisPage() {
  const [ejemplo, setEjemplo] = useState(EJEMPLOS[0].id);
  const [estado, setEstado] = useState(null);

  async function simular() {
    setEstado({ cargando: true });
    try { setEstado({ resultado: await analizarEjemplo(ejemplo) }); }
    catch (e) { setEstado({ error: e.message }); }
  }

  return (
    <>
      <div className="notice"><strong>Demostración con datos de ejemplo.</strong> Este módulo ilustra la revisión de bases; no ejecuta un modelo de IA ni carga documentos.</div>
      <div className="module-grid">
        <section className="card panel"><span className="badge blue">Paso 1</span><h2>Seleccionar oportunidad</h2>
          <label className="field">Licitación de ejemplo
            <select value={ejemplo} onChange={e => { setEjemplo(e.target.value); setEstado(null); }}>
              {EJEMPLOS.map(x => <option key={x.id} value={x.id}>{x.nombre}</option>)}
            </select></label>
          <div className="document-preview"><span className="document-symbol">↥</span><strong>Bases técnicas y administrativas</strong><p>En la versión final podrás adjuntar archivos PDF y revisar sus requisitos.</p><span className="badge">Carga de archivos · próximamente</span></div>
          <button className="primary" onClick={simular} disabled={estado?.cargando}>Simular análisis</button>
        </section>
        <section className="card panel"><div className="section-title"><h2>Resumen de revisión</h2><span className="badge amber">Validación humana</span></div>
          <div aria-live="polite"><Resultado estado={estado} /></div></section>
      </div>
      <section className="card panel spaced"><h2>Cómo funcionará</h2><div className="steps"><div><b>01 · Leer bases</b><p>Identificar servicios, fechas y presupuesto.</p></div><div><b>02 · Contrastar</b><p>Comparar requisitos con la capacidad del hotel.</p></div><div><b>03 · Validar</b><p>Confirmar alertas antes de tomar una decisión.</p></div></div></section>
    </>
  );
}
