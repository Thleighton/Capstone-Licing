// Router mínimo basado en el hash (#dashboard, #licitaciones, ...).
// Se mantiene el hash para no romper los enlaces existentes ni los redirect de Supabase.
import { useEffect, useState } from "react";
import { resolverRuta } from "./resolverRuta";
const leer = () => location.hash.slice(1).split("?")[0];

export function useHashRoute(modulos, inicial) {
  const resolver = () => resolverRuta(modulos, leer(), inicial);
  const [ruta, setRuta] = useState(resolver);
  useEffect(() => {
    const onChange = () => {
      const actual = leer();
      const siguiente = resolverRuta(modulos, actual, inicial);
      if (siguiente && actual !== siguiente) history.replaceState(null, "", location.pathname + location.search + "#" + siguiente);
      setRuta(siguiente);
    };
    onChange();
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, [modulos, inicial]);
  return ruta;
}

export const irA = id => { if (location.hash !== "#" + id) location.hash = id; };

