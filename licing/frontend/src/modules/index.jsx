// ============================================================
// REGISTRO DE MÓDULOS
// El orden de esta lista es el orden del menú lateral.
// Para crear un módulo nuevo: copia la carpeta _plantilla, cambia
// su index.js y agrégalo aquí. No hace falta tocar App.jsx.
// ============================================================
import dashboard from "./dashboard";
import oportunidades from "./oportunidades";
import comprasAgiles from "./compras-agiles";
import perfilHotel from "./perfil-hotel";
import disponibilidad from "./disponibilidad";
import clientes from "./clientes";
import analisis from "./analisis";
import seguimiento from "./seguimiento";
import reportes from "./reportes";
import configuracion from "./configuracion";
import { moduloHabilitado } from "./habilitados";

// Mostrar el menú completo de módulos habilitados.
export const SOLO_DASHBOARD = false;

export const TODOS_LOS_MODULOS = [
  dashboard,
  oportunidades,
  comprasAgiles,
  perfilHotel,
  disponibilidad,
  clientes,
  analisis,
  seguimiento,
  reportes,
  configuracion,
];

// Las pantallas, las rutas y el menú incluyen solo los módulos habilitados.
export const MODULOS = TODOS_LOS_MODULOS.filter(m => moduloHabilitado(m.id));
export const MODULOS_MENU = SOLO_DASHBOARD ? [dashboard] : MODULOS;
export const MODULO_INICIAL = dashboard;

// Componentes globales que exponen los módulos (diálogos que se abren desde cualquier página).
export function Globales() {
  return MODULOS.filter(m => m.Global).map(({ id, Global }) => <Global key={id} />);
}

