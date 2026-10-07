// Estado compartido de las licitaciones leídas desde "Licing/Datos".
// Lo usan el Dashboard, Oportunidades y la barra superior (búsqueda y estado de conexión).
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { contar, datosJson } from "../api/client";
import { getConfig } from "../api/config";
import { SELECT_EJECUCIONES, SELECT_LICITACIONES } from "./licitaciones";

const Ctx = createContext(null);
export const useLicitaciones = () => useContext(Ctx);

export function LicitacionesProvider({ children }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [runs, setRuns] = useState([]);
  const [status, setStatus] = useState({ kind: "", text: "Conectando..." });
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(true);
  const [actualizado, setActualizado] = useState(null);
  // Búsqueda y filtros (la barra superior escribe aquí; Oportunidades los aplica)
  const [q, setQ] = useState("");
  const [filtros, setFiltros] = useState({ tipo: "", soloValidas: false, visibles: false });
  // Ficha de detalle abierta (cualquier módulo puede abrirla)
  const [fichaId, setFichaId] = useState(null);

  const cargar = useCallback(async () => {
    setError(""); setCargando(true);
    setStatus({ kind: "", text: "Conectando..." });
    const t0 = performance.now();
    try {
      const [r, t, e] = await Promise.all([
        datosJson(SELECT_LICITACIONES),
        contar("licitacion"),
        datosJson(SELECT_EJECUCIONES).catch(() => []),
      ]);
      setRows(r); setTotal(t); setRuns(e); setActualizado(new Date());
      setStatus({ kind: "ok", text: "Conectado a Licing/Datos (" + Math.round(performance.now() - t0) + " ms)" });
    } catch (e) {
      setRows([]); setRuns([]);
      setStatus({ kind: "err", text: "Sin conexión" });
      setError("No se pudo leer la base de datos.\n" + e.message +
        "\n\nRevisa en el .env / Vercel: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY de Licing/Datos, y USUARIOS_URL / USUARIOS_ANON_KEY de Licing/Usuarios.");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const value = {
    rows, total, runs, status, error, cargando, actualizado, cargar,
    q, setQ, filtros, setFiltros: p => setFiltros(f => ({ ...f, ...p })),
    fichaId, abrirFicha: setFichaId, cerrarFicha: () => setFichaId(null),
    datosHost: getConfig().DATOS_HOST,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
