// PLANTILLA DE MÓDULO — copia esta carpeta, renómbrala y ajusta estos campos.
// Luego regístralo en src/modules/index.jsx.
import PlantillaPage from "./PlantillaPage";

export default {
  id: "plantilla",            // hash de la URL (#plantilla) — único
  nav: "Plantilla",           // texto en el menú lateral
  icono: "file",              // ver core/ui/Icon.jsx
  titulo: "Módulo plantilla", // título grande de la página
  descripcion: "Describe en una línea qué resuelve este módulo.",
  responsable: "Nombre Apellido",
  epicas: [],                 // ej. ["E6"]
  Page: PlantillaPage,
  // HeaderExtra: Componente opcional junto al título
  // Global: Componente opcional siempre montado (diálogos)
};
