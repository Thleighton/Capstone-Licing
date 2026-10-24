import { forwardRef } from "react";
import { moduloHabilitado } from "../../modules/habilitados";

// Encabezado común de cada página. `extra` permite que un módulo agregue un botón junto al título.
const PageHeading = forwardRef(function PageHeading({ titulo, descripcion, extra, mostrarAccion = true }, ref) {
  return (
    <header className="page-heading">
      <div>
        <p className="eyebrow">PLAZA SAN FRANCISCO / GESTIÓN COMERCIAL</p>
        <div className="page-title-row"><h1 ref={ref} tabIndex={-1}>{titulo}</h1>{extra}</div>
        <p>{descripcion}</p>
      </div>
      {mostrarAccion && moduloHabilitado("formulario") && <a className="button primary" href="#formulario">+ Definir criterios</a>}
    </header>
  );
});
export default PageHeading;

