// Reportes con DATOS DE EJEMPLO. Próximo paso: GET /api/reportes/<tipo> con datos reales.
import { useState } from "react";

const REPORTES = [
  { nombre: "Resumen comercial", icono: "↗", texto: "Oportunidades detectadas, calificadas y resultados del período.", filas: [["Detectadas", 24], ["Calificadas", 12], ["Participadas", 6], ["Adjudicadas", 2]] },
  { nombre: "Rendimiento por servicio", icono: "◎", texto: "Distribución de alojamiento, salones y banquetería.", filas: [["Alojamiento", 12], ["Salones", 8], ["Banquetería", 4]] },
  { nombre: "Motivos de descarte", icono: "≡", texto: "Razones para excluir oportunidades y ajustar los criterios.", filas: [["Fuera de región", 6], ["Servicio no disponible", 4], ["Plazo insuficiente", 3]] },
];

export default function ReportesPage() {
  const [sel, setSel] = useState(null);
  const max = sel ? Math.max(...sel.filas.map(r => r[1])) : 1;
  return (
    <>
      <div className="notice"><strong>Reportes tentativos.</strong> La vista previa utiliza datos de ejemplo; no genera documentos oficiales.</div>
      <div className="report-grid">
        {REPORTES.map(r => (
          <section className="card panel" key={r.nombre}><div className="report-icon">{r.icono}</div><h2>{r.nombre}</h2><p>{r.texto}</p>
            <button onClick={() => setSel(r)}>Ver ejemplo</button></section>
        ))}
      </div>
      <section className="card panel spaced" aria-live="polite">
        {!sel ? <><h2>Vista previa de reporte</h2><p className="empty">Selecciona un reporte para revisar su estructura.</p></> : <>
          <div className="section-title"><h2>{sel.nombre}</h2><span className="badge amber">Datos de ejemplo</span></div>
          <p className="sub">Período ilustrativo · no corresponde a los registros reales.</p>
          {sel.filas.map(([label, v]) => (
            <div className="rubro" key={label}><div className="row"><b>{label}</b><span>{v} oportunidades</span></div>
              <div className="bar"><i style={{ width: v / max * 100 + "%" }} /></div></div>
          ))}
        </>}
      </section>
    </>
  );
}
