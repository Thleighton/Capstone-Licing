import "./resumen-analisis.css";

const NOMBRES_CRITERIO = {
  vigencia: "la vigencia",
  ubicacion: "el lugar de prestación",
  pertinencia: "la relación con los servicios del hotel",
  servicio: "el servicio solicitado",
};

function criterioPendiente(criterios = []) {
  return criterios
    .filter(c => ["sin_informacion", "por_verificar"].includes(c.resultado))
    .map(c => NOMBRES_CRITERIO[c.codigo] || c.nombre || c.codigo)
    .filter(Boolean);
}

function clean(value, max = 180) {
  if (typeof value !== "string") return "";
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

export default function ResumenAnalisis({
  estado,
  motivo,
  criterios = [],
  items = [],
  descripcion,
  hallazgos = [],
  documentosLeidos = false,
  fechaCierre,
  monto,
  lugar,
}) {
  const pendientes = criterioPendiente(criterios);
  const servicios = [...new Set(items.map(i => clean(i.nombre_producto || i.nombre, 55)).filter(Boolean))].slice(0, 3);
  const hallazgo = hallazgos.find(h => h && (h.ubicacion || h.participantes || h.fechas || h.duracion || h.horario || h.presupuesto));
  const datos = [
    ["Cierre", fechaCierre !== "-" ? fechaCierre : ""],
    ["Monto informado", monto !== "-" ? monto : ""],
    ["Lugar del evento", hallazgo?.ubicacion?.resumen || lugar],
    ["Participantes", hallazgo?.participantes?.resumen],
    ["Fechas", hallazgo?.fechas?.resumen],
    ["Duración", hallazgo?.duracion?.resumen],
    ["Horario", hallazgo?.horario?.resumen],
    ["Monto indicado en bases", hallazgo?.presupuesto?.resumen],
  ].filter(([, value]) => value).map(([label, value]) => ({ label, value: clean(value, 100) }));

  let orientacion = "Revisar la ficha y confirmar los requisitos antes de decidir.";
  if (["preseleccionada", "posible_oportunidad"].includes(estado)) {
    orientacion = "Hay señales compatibles con el hotel. Confirmar capacidad, disponibilidad y condiciones antes de cotizar.";
  } else if (["revision_manual", "revision_necesaria", "pendiente_evaluacion"].includes(estado)) {
    orientacion = pendientes.length
      ? `Falta confirmar ${pendientes.join(" y ")}; mantener en revisión hasta contar con ese dato.`
      : "La información disponible no permite confirmar todos los requisitos; mantener en revisión.";
  } else if (["descartada_por_regla", "descartada"].includes(estado)) {
    orientacion = "El filtro encontró una incompatibilidad explícita. Revisar el motivo y los ítems antes de cerrar la decisión.";
  }

  return <section className={`resumen-analisis resumen-analisis--${estado || "pendiente"}`} aria-label="Resumen del análisis automático">
    <header className="resumen-analisis__header">
      <span className="resumen-analisis__icono" aria-hidden="true">✓</span>
      <div><p>LECTURA DE LICING</p><h3>Resumen para decidir</h3></div>
      <small>Según la ficha, los ítems{documentosLeidos ? " y las bases leídas" : ""}</small>
    </header>
    {motivo && <div className="resumen-analisis__conclusion"><strong>Conclusión del filtro</strong><p>{clean(motivo, 300)}</p></div>}
    {descripcion && <div className="resumen-analisis__solicitud"><strong>Qué solicitan</strong><p>{clean(descripcion, 260)}</p></div>}
    {servicios.length > 0 && <div className="resumen-analisis__items"><strong>Ítems principales</strong><p>{servicios.join(" · ")}{items.length > servicios.length ? ` · y ${items.length - servicios.length} más` : ""}</p></div>}
    {datos.length > 0 && <dl className="resumen-analisis__datos">{datos.map(d => <div key={d.label}><dt>{d.label}</dt><dd>{d.value}</dd></div>)}</dl>}
    {pendientes.length > 0 && <p className="resumen-analisis__pendientes"><strong>Por confirmar:</strong> {pendientes.join(" · ")}.</p>}
    <div className="resumen-analisis__accion"><strong>Siguiente paso</strong><p>{orientacion}</p></div>
    <small className="resumen-analisis__nota">Se muestran datos disponibles. Los campos ausentes no se consideran confirmados; este resumen no cambia la clasificación.</small>
  </section>;
}
