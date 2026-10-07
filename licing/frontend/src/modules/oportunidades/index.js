// Módulo Oportunidades — Épicas E1 (obtención), E2 (filtrado) y E3 (validación de ID).
import OportunidadesPage from "./OportunidadesPage";
import FichaLicitacion from "./components/FichaLicitacion";

export default {
  id: "oportunidades",
  nav: "Oportunidades",
  icono: "briefcase",
  titulo: "Oportunidades",
  descripcion: "Explora las licitaciones y revisa su información de origen.",
  responsable: "Diego Sandoval",
  epicas: ["E1", "E2", "E3"],
  Page: OportunidadesPage,
  Global: FichaLicitacion, // diálogo de ficha, se puede abrir desde cualquier módulo con abrirFicha(id)
};
