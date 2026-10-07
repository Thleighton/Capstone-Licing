// Módulo Perfil del hotel — Épica E2 (criterios de búsqueda y filtrado semántico).
import PerfilHotelPage from "./PerfilHotelPage";
import { BotonAyuda, GuiaFormulario } from "./components/GuiaFormulario";

export default {
  id: "formulario", // se mantiene el hash #formulario del prototipo
  nav: "Perfil del hotel",
  icono: "file",
  titulo: "Perfil del hotel",
  descripcion: "La oferta y los criterios del cliente, como punto de partida.",
  responsable: "Miguel Mancilla",
  epicas: ["E2"],
  Page: PerfilHotelPage,
  HeaderExtra: BotonAyuda,
  Global: GuiaFormulario,
};
