// Consultas autenticadas a Core; filtros y paginación en el servidor.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { apiJson } from "../api/client";
const Ctx = createContext(null);
export const useLicitaciones = () => useContext(Ctx);
const LIMITE = 100;
export function LicitacionesProvider({ children }) {
  const [rows, setRows] = useState([]), [total, setTotal] = useState(0);
  const [dashboard, setDashboard] = useState(null), [runs, setRuns] = useState([]);
  const [status, setStatus] = useState({ kind: "", text: "Conectando..." });
  const [error, setError] = useState(""), [cargando, setCargando] = useState(true);
  const [actualizado, setActualizado] = useState(null);
  const [q, escribirQ] = useState("");
  const [filtros, escribirFiltros] = useState({ soloAbiertas: false, region: "", visibles: false });
  const [pagina, setPagina] = useState(0), [fichaId, setFichaId] = useState(null);
  const peticion = useRef(0);
  const cargar = useCallback(async () => {
    const id = ++peticion.current;
    setError(""); setCargando(true); setStatus({ kind: "", text: "Consultando..." });
    try {
      const parametros = new URLSearchParams({ q, region: filtros.region, solo_abiertas: String(filtros.soloAbiertas), limite: String(LIMITE), offset: String(pagina * LIMITE) });
      const [listado, resumen, ejecuciones] = await Promise.all([
        apiJson("/api/licitaciones?" + parametros), apiJson("/api/dashboard"), apiJson("/api/ingestas"),
      ]);
      if (id !== peticion.current) return;
      setRows(listado.items); setTotal(listado.total); setDashboard(resumen); setRuns(ejecuciones);
      setActualizado(new Date()); setStatus({ kind: "ok", text: "Conectado" });
    } catch (e) {
      if (id !== peticion.current) return;
      setRows([]); setTotal(0); setDashboard(null); setRuns([]); setActualizado(null);
      setStatus({ kind: "err", text: "Sin conexión" }); setError("No se pudieron consultar las licitaciones. " + e.message);
    } finally { if (id === peticion.current) setCargando(false); }
  }, [q, filtros.region, filtros.soloAbiertas, pagina]);
  useEffect(() => {
    setCargando(true);
    const timer = setTimeout(cargar, 250);
    return () => { clearTimeout(timer); peticion.current++; };
  }, [cargar]);
  return <Ctx.Provider value={{
    rows, total, dashboard, runs, status, error, cargando, actualizado, cargar, pagina, setPagina, limite: LIMITE,
    q, setQ: texto => { escribirQ(texto); setPagina(0); },
    filtros, setFiltros: cambios => {
      escribirFiltros(f => ({ ...f, ...cambios }));
      if ("region" in cambios || "soloAbiertas" in cambios) setPagina(0);
    },
    fichaId, abrirFicha: setFichaId, cerrarFicha: () => setFichaId(null),
  }}>{children}</Ctx.Provider>;
}
