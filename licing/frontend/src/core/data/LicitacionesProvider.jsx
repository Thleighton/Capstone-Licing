// Consultas autenticadas a Core; filtros y paginación en el servidor.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { apiJson } from "../api/client";
const Ctx = createContext(null);
export const useLicitaciones = () => useContext(Ctx);
const LIMITE = 100;
export function LicitacionesProvider({ children }) {
  const [rows, setRows] = useState([]), [total, setTotal] = useState(0);
  const [dashboard, setDashboard] = useState(null);
  const [dashboardError, setDashboardError] = useState("");
  const [dashboardCargando, setDashboardCargando] = useState(true);
  const [error, setError] = useState(""), [cargando, setCargando] = useState(true);
  const [actualizado, setActualizado] = useState(null);
  const [q, escribirQ] = useState("");
  const [filtros, escribirFiltros] = useState({ soloAbiertas: false, region: "", visibles: false });
  const [pagina, setPagina] = useState(0), [fichaId, setFichaId] = useState(null);
  const listaControl = useRef(null), resumenControl = useRef(null);
  const cargarLista = useCallback(async () => {
    listaControl.current?.abort();
    const control = new AbortController(); listaControl.current = control;
    setError(""); setCargando(true);
    try {
      const parametros = new URLSearchParams({ q, region: filtros.region, solo_abiertas: String(filtros.soloAbiertas), limite: String(LIMITE), offset: String(pagina * LIMITE) });
      const listado = await apiJson("/api/licitaciones?" + parametros, { signal: control.signal });
      if (control.signal.aborted) return;
      setRows(listado.items); setTotal(listado.total);
    } catch (e) {
      if (!control.signal.aborted) setError("No se pudieron actualizar las licitaciones. " + e.message);
    } finally { if (!control.signal.aborted) setCargando(false); }
  }, [q, filtros.region, filtros.soloAbiertas, pagina]);
  const cargarResumen = useCallback(async () => {
    resumenControl.current?.abort();
    const control = new AbortController(); resumenControl.current = control;
    setDashboardError(""); setDashboardCargando(true);
    try {
      const resumen = await apiJson("/api/dashboard", { signal: control.signal });
      if (control.signal.aborted) return;
      setDashboard(resumen); setActualizado(new Date());
    } catch (e) {
      if (!control.signal.aborted) setDashboardError("No se pudo actualizar el resumen. " + e.message);
    } finally { if (!control.signal.aborted) setDashboardCargando(false); }
  }, []);
  const cargar = useCallback(() => Promise.all([cargarLista(), cargarResumen()]), [cargarLista, cargarResumen]);
  useEffect(() => {
    setCargando(true);
    const timer = setTimeout(cargarLista, 250);
    return () => { clearTimeout(timer); listaControl.current?.abort(); };
  }, [cargarLista]);
  useEffect(() => {
    cargarResumen();
    return () => resumenControl.current?.abort();
  }, [cargarResumen]);
  const status = error || dashboardError ? { kind: "err", text: "Actualización incompleta" }
    : cargando || dashboardCargando ? { kind: "", text: "Actualizando..." }
    : { kind: "ok", text: "Conectado" };
  return <Ctx.Provider value={{
    rows, total, dashboard, dashboardError, dashboardCargando, status, error, cargando, actualizado, cargar, cargarResumen, pagina, setPagina, limite: LIMITE,
    q, setQ: texto => { escribirQ(texto); setPagina(0); },
    filtros, setFiltros: cambios => {
      escribirFiltros(f => ({ ...f, ...cambios }));
      if ("region" in cambios || "soloAbiertas" in cambios) setPagina(0);
    },
    fichaId, abrirFicha: setFichaId, cerrarFicha: () => setFichaId(null),
  }}>{children}</Ctx.Provider>;
}
