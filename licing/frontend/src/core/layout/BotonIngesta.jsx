import { useState } from "react";
import { apiJson } from "../api/client";
import { useLicitaciones } from "../data/LicitacionesProvider";
import { useAuth } from "../auth/AuthProvider";

export default function BotonIngesta({ fuente = "licitaciones" }) {
  const { perfil } = useAuth();
  const { cargar } = useLicitaciones();
  const compras = fuente === "compras-agiles";
  const [ocupado, setOcupado] = useState(false), [mensaje, setMensaje] = useState("");
  async function obtener() {
    setOcupado(true); setMensaje("");
    try {
      const r = await apiJson(`/api/ingesta/${compras ? "compras-agiles" : "licitaciones"}/lote/ejecutar?limite=${compras ? 20 : 1}`, { method: "POST" });
      setMensaje(r.errores?.length ? "La ingesta terminó con errores. Revisa la actividad reciente."
        : r.procesados ? compras ? `${r.procesados} Compras Ágiles guardadas.` : "Licitación guardada."
        : compras ? "No se incorporaron nuevas Compras Ágiles en este turno." : "No hay licitaciones nuevas para descargar.");
      await cargar();
    } catch (e) { setMensaje(e.message); }
    finally { setOcupado(false); }
  }
  if (perfil?.rol !== "administrador") return null;
  return <div><button type="button" disabled={ocupado} onClick={obtener}>{ocupado ? "Obteniendo…" : compras ? "Obtener Compras Ágiles" : "Obtener licitaciones"}</button>
    <span className="sub" role="status">{mensaje}</span></div>;
}
