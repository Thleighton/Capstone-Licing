// Ejemplo mínimo: lee datos con la sesión del usuario y llama al backend del módulo.
import { useEffect, useState } from "react";
import { apiFetch } from "../../core/api/client";

export default function PlantillaPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch("/api/plantilla/hola").then(r => r.json()).then(setData).catch(e => setError(e.message));
  }, []);

  return (
    <section className="card panel">
      <h2>Módulo plantilla</h2>
      {error ? <p className="msg err">{error}</p> : <pre>{JSON.stringify(data, null, 2)}</pre>}
    </section>
  );
}
