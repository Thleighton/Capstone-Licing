import { Fragment, forwardRef } from "react";
import { IMPORTANCE, INTAKE_GROUPS } from "../campos";

// Resumen de lo declarado (no se guarda todavía).
const ResumenPerfil = forwardRef(function ResumenPerfil({ data }, ref) {
  return (
    <section ref={ref} className="card panel preview" aria-live="polite">
      <span className="badge blue">Perfil del hotel · no guardada</span>
      <h2 className="spaced">{data.get("perfil")}</h2>
      <p className="sub">Información declarada por el cliente. Pendiente de contrastar con la solicitud y la agenda real.</p>
      {INTAKE_GROUPS.map(g => {
        const entries = g.fields.map(([name, label, type]) => [label, type === "checks" ? (data.getAll(name).join(", ") || "Por confirmar") : data.get(name) || "Por confirmar"]);
        if (g.matrix) entries.unshift(...IMPORTANCE.map(([k, label]) => [label, data.get("importancia_" + k) || "Por definir"]));
        return (
          <div key={g.title}>
            <h3>{g.title}</h3>
            <dl className="kv">{entries.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}</dl>
          </div>
        );
      })}
      <div className="notice"><strong>Validación humana pendiente.</strong> Este resumen no confirma compatibilidad ni disponibilidad. Antes de participar, el equipo debe revisar capacidades, requisitos y agenda.</div>
    </section>
  );
});
export default ResumenPerfil;
