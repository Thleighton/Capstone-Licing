import { useEffect, useState } from "react";
import { apiJson } from "../../../core/api/client";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import { dinero, fecha } from "../../../core/ui/format";
import { abrirCompraAgil } from "../store";
import { ETIQUETAS, TONOS, plazo } from "../comun";

const LIMITE = 25;

// Clasificación guardada en LicitacionesFiltradas, ordenada por cierre más próximo.
export default function VistaPreseleccion({ q, version }) {
  const [clasificacion, setClasificacion] = useState("preseleccionada");
  const [offset, setOffset] = useState(0);
  const [datos, setDatos] = useState({ filas: [], total: 0, pendientes: 0 });
  const [cargando, setCargando] = useState(true), [error, setError] = useState("");
  useEffect(() => { setOffset(0); }, [q, clasificacion]);
  useEffect(() => {
    const control = new AbortController();
    setCargando(true);
    const parametros = new URLSearchParams({ clasificacion, q, limite: String(LIMITE), offset: String(offset) });
    apiJson("/api/compras-agiles/preseleccion?" + parametros, { signal: control.signal })
      .then(r => { setDatos(r); setError(""); })
      .catch(e => { if (!control.signal.aborted) setError(e.message); })
      .finally(() => { if (!control.signal.aborted) setCargando(false); });
    return () => control.abort();
  }, [clasificacion, q, offset, version]);
  const vacio = clasificacion === "preseleccionada"
    ? "No hay posibles oportunidades entre las Compras Ágiles evaluadas. Revisa «Revisión necesaria» o la vista Todas."
    : "No hay Compras Ágiles en esta clasificación.";
  return <>
    <div className="filtros ca-filtros">
      <label>Clasificación <select value={clasificacion} onChange={e => setClasificacion(e.target.value)}>
        <option value="">Todas</option>{Object.entries(ETIQUETAS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select></label>
      <span aria-live="polite">{datos.total} {datos.total === 1 ? "resultado" : "resultados"}</span>
      {datos.pendientes > 0 && <span className="badge violet">{datos.pendientes} por evaluar en los próximos turnos</span>}
    </div>
    <div className="scroll" aria-busy={cargando}><table className="ca-tabla">
      <colgroup><col style={{ width: 185 }} /><col /><col style={{ width: 130 }} /><col style={{ width: 135 }} /><col style={{ width: 150 }} /></colgroup>
      <thead><tr><th>Código</th><th>Compra Ágil</th><th>Cierre</th><th>Presupuesto</th><th>Preselección</th></tr></thead>
      <tbody>{datos.filas.map(f => {
        const aviso = plazo(f.fecha_cierre);
        return <tr key={f.id} onClick={() => abrirCompraAgil(f.id)}
          className={f.clientes_importantes?.length ? "opportunity-important" : undefined}>
          <td><button className="cod" onClick={e => { e.stopPropagation(); abrirCompraAgil(f.id); }}>{f.codigo_externo}</button>
            {f.url_oficial && <div className="sub"><a href={f.url_oficial} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>Mercado Público ↗</a></div>}</td>
          <td className="nom"><TituloLicitacion as="div" licitacion={f} />
            <ClienteImportanteBadge clientes={f.clientes_importantes} />
            <p className="ca-motivo">{f.motivo_seleccion}</p></td>
          <td>{fecha(f.fecha_cierre)}{aviso && <div><span className="ca-plazo" data-nivel={aviso.nivel}>{aviso.texto}</span></div>}</td>
          <td>{f.monto_disponible_clp == null ? "-" : dinero(f.monto_disponible_clp, "CLP")}<div className="sub">{f.region_comprador}</div></td>
          <td><span className={"badge " + (TONOS[f.estado_seleccion] || "")}>{ETIQUETAS[f.estado_seleccion] || f.estado_seleccion}</span></td>
        </tr>;
      })}</tbody>
    </table>
    {error ? <div className="msg err" role="alert">No se pudo consultar la preselección. {error}</div>
      : cargando ? <p className="msg">Cargando preselección…</p> : !datos.filas.length ? <p className="msg">{vacio}</p> : null}</div>
    {datos.total > LIMITE && <div className="card-head ca-paginas">
      <span>{offset + 1}–{Math.min(offset + LIMITE, datos.total)} de {datos.total}</span>
      <div><button disabled={cargando || offset === 0} onClick={() => setOffset(o => o - LIMITE)}>Anterior</button>{" "}
        <button disabled={cargando || offset + LIMITE >= datos.total} onClick={() => setOffset(o => o + LIMITE)}>Siguiente</button></div>
    </div>}
  </>;
}
