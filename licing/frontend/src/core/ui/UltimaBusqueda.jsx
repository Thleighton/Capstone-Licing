import { useEffect, useState } from "react";
import { apiJson } from "../api/client";

const FUENTES = [
  { id: "licitaciones", nombre: "Licitaciones" },
  { id: "compra_agil", nombre: "Compras Ágiles" },
];

function fecha(valor) {
  if (!valor) return "Sin búsquedas registradas";
  return new Intl.DateTimeFormat("es-CL", {
    dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago",
  }).format(new Date(valor));
}

export default function UltimaBusqueda({ fuente }) {
  const [ultima, setUltima] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let control = new AbortController();
    const cargar = () => {
      control.abort();
      control = new AbortController();
      const solicitud = control;
      apiJson("/api/ingestas?limite=100", { signal: solicitud.signal })
      .then(filas => {
        const registro = filas.find(f => f.fuente === fuente && f.estado !== "en_curso")
          || filas.find(f => f.fuente === fuente);
        setUltima(registro || null); setError(false);
      })
      .catch(() => { if (!solicitud.signal.aborted) setError(true); });
    };
    cargar();
    const intervalo = window.setInterval(cargar, 60_000);
    window.addEventListener("licing:ingesta-actualizada", cargar);
    return () => { control.abort(); window.clearInterval(intervalo); window.removeEventListener("licing:ingesta-actualizada", cargar); };
  }, [fuente]);
  const nombre = FUENTES.find(f => f.id === fuente)?.nombre || "Datos";
  const marcaTiempo = ultima?.fin || ultima?.inicio;
  return <p className="ultima-busqueda" aria-live="polite">
    <strong>Última búsqueda de {nombre}:</strong>{" "}
    {error ? "No se pudo consultar el historial." : fecha(marcaTiempo)}
    {ultima?.estado === "en_curso" && " · búsqueda en curso"}
    {ultima?.estado === "parcial" && " · carga parcial"}
    {ultima?.estado === "error" && " · última carga con error"}
  </p>;
}
