// Router mínimo basado en el hash (#dashboard, #oportunidades, ...).
// Se mantiene el hash para no romper los enlaces existentes ni los redirect de Supabase.
import { useEffect, useState } from "react";

const leer = () => location.hash.slice(1).split("?")[0];

export function useHashRoute() {
  const [ruta, setRuta] = useState(leer);
  useEffect(() => {
    const onChange = () => setRuta(leer());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return ruta;
}

export const irA = id => { if (location.hash !== "#" + id) location.hash = id; };
