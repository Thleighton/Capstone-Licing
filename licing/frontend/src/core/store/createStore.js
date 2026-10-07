// Store global mínimo (sin librerías) para compartir estado simple entre módulos.
// Uso:
//   export const miStore = createStore({ valor: 1 });
//   const valor = useStore(miStore, s => s.valor);
//   miStore.set({ valor: 2 });
import { useSyncExternalStore } from "react";

export function createStore(inicial) {
  let estado = inicial;
  const subs = new Set();
  return {
    get: () => estado,
    set: parcial => {
      estado = { ...estado, ...(typeof parcial === "function" ? parcial(estado) : parcial) };
      subs.forEach(fn => fn());
    },
    subscribe: fn => { subs.add(fn); return () => subs.delete(fn); },
  };
}

export function useStore(store, selector = s => s) {
  return useSyncExternalStore(store.subscribe, () => selector(store.get()));
}
