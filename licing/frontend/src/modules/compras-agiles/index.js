// Módulo Compras Ágiles — Épicas E1 (obtención) y E2 (filtrado).
import ComprasAgilesPage, { ObtenerComprasAgiles } from "./ComprasAgilesPage";
import FichaCompraAgil from "./components/FichaCompraAgil";

export default {
  id: "compras-agiles",
  nav: "Compras Ágiles",
  icono: "bolt",
  titulo: "Compras Ágiles",
  descripcion: "Cotizaciones rápidas de Mercado Público y su preselección para el hotel.",
  responsable: "Diego Sandoval",
  epicas: ["E1", "E2"],
  Page: ComprasAgilesPage,
  HeaderExtra: ObtenerComprasAgiles,
  Global: FichaCompraAgil, // ficha que se abre desde la página o el dashboard con abrirCompraAgil(id)
};
