// Dibuja un campo del formulario a partir de su definición en campos.js.
export default function Campo({ def: [name, label, type, options, required] }) {
  const common = { name, required: Boolean(required) };
  if (type === "checks") {
    return (
      <div className="wide"><h3 className="field-heading">{label}</h3>
        <div className="check-grid">{options.map(v => <label key={v}><input type="checkbox" {...common} value={v} />{v}</label>)}</div>
      </div>
    );
  }
  let input;
  if (type === "select") {
    input = <select {...common} defaultValue=""><option value="">Por confirmar</option>{options.map(v => <option key={v}>{v}</option>)}</select>;
  } else if (type === "textarea") {
    input = <textarea {...common} rows={3} placeholder={options || ""} />;
  } else {
    const num = type === "number"
      ? { min: ["capacidad_max", "asistentes"].includes(name) ? "1" : name === "duracion" ? "0.5" : "0", step: name === "duracion" ? "0.5" : "1" }
      : {};
    input = <input {...common} type={type} placeholder={options || ""} {...num} />;
  }
  return <label className={type === "textarea" ? "wide" : undefined}>{label}{required ? " *" : ""}{input}</label>;
}
