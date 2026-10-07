// Módulo Salones y disponibilidad — apoyo a E6 (viabilidad) y al encaje de solicitudes.
import DisponibilidadPage from "./DisponibilidadPage";

export default {
  id: "disponibilidad",
  nav: "Salones y disponibilidad",
  icono: "hotel",
  titulo: "Salones del hotel",
  descripcion: "Hotel Plaza San Francisco · espacios dentro de un único edificio.",
  responsable: "Thomas Leighton",
  epicas: ["E6"],
  Page: DisponibilidadPage,
};
