import { useState } from "react";
import { apiJson } from "../api/client";
import { useLicitaciones } from "../data/LicitacionesProvider";

export default function BotonIngesta() {
  const { cargar } = useLicitaciones();
  const [ocupado, setOcupado] = useState(false), [mensaje, setMensaje] = useState("");
  async function obtener() {
    setOcupado(true); setMensaje("");
    try {
      const r = await apiJson("/api/ingesta/licitaciones/lote/ejecutar?limite=1", { method: "POST" });
      setMensaje(r.errores.length ? "La ingesta terminó con errores. Revisa la actividad reciente." : r.procesados ? "Licitación guardada." : "No hay licitaciones nuevas para descargar.");
      await cargar();
    } catch (e) { setMensaje(e.message); }
    finally { setOcupado(false); }
  }
  return <div><button disabled={ocupado} onClick={obtener}>{ocupado ? "Obteniendo…" : "Obtener licitaciones"}</button>
    <span className="sub" role="status">{mensaje}</span></div>;
}
