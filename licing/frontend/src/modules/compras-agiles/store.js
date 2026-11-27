// Ficha de Compra Ágil abierta desde cualquier módulo (página propia o dashboard).
import { createStore } from "../../core/store/createStore";

export const fichaCompraAgil = createStore({ id: null, versionRevision: 0 });
export const abrirCompraAgil = id => fichaCompraAgil.set({ id });
export const cerrarCompraAgil = () => fichaCompraAgil.set({ id: null });
export const notificarRevisionCompraAgil = () => fichaCompraAgil.set(s => ({
  versionRevision: s.versionRevision + 1,
}));
