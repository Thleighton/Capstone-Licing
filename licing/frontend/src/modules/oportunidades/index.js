// Módulo Licitaciones — Épicas E1 (obtención), E2 (filtrado) y E3 (validación de ID).
import LicitacionesPage from "./OportunidadesPage";
import FichaLicitacion from "./components/FichaLicitacion";

export default {
  id: "licitaciones",
  aliases: ["oportunidades"],
  nav: "Licitaciones",
  icono: "briefcase",
  titulo: "Licitaciones",
  descripcion: "Consulta los indicadores, descarga el listado y revisa la preselección para el hotel.",
  responsable: "Diego Sandoval",
  epicas: ["E1", "E2", "E3"],
  Page: LicitacionesPage,
  Global: FichaLicitacion, // diálogo de ficha, se puede abrir desde cualquier módulo con abrirFicha(id)
};
