// Módulo Clientes — historial comercial que ajusta la prioridad (apoyo a E2/E7).
import ClientesPage from "./ClientesPage";

export default {
  id: "clientes",
  nav: "Clientes",
  icono: "star",
  titulo: "Clientes e historial",
  descripcion: "Reconoce relaciones previas y prioriza oportunidades con contexto comercial.",
  responsable: "Thomas Leighton",
  epicas: ["E7"],
  Page: ClientesPage,
};
