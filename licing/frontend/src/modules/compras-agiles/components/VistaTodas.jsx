import { useEffect, useState } from "react";
import { apiJson } from "../../../core/api/client";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import { dinero, fecha } from "../../../core/ui/format";
import { abrirCompraAgil } from "../store";
import { ETIQUETAS, TONOS, plazo } from "../comun";

const LIMITE = 50;

// Todas las Compras Ágiles guardadas por Core, con búsqueda y filtros en el servidor.
export default function VistaTodas({ q, version }) {
  const [region, setRegion] = useState(""), [soloAbiertas, setSoloAbiertas] = useState(true);
  const [offset, setOffset] = useState(0);
  const [datos, setDatos] = useState({ items: [], total: 0 });
  const [cargando, setCargando] = useState(true), [error, setError] = useState("");
  useEffect(() => { setOffset(0); }, [q, region, soloAbiertas]);
  useEffect(() => {
    const control = new AbortController();
    setCargando(true);
    const espera = setTimeout(() => {
      const parametros = new URLSearchParams({ q, region, solo_abiertas: String(soloAbiertas), limite: String(LIMITE), offset: String(offset) });
      apiJson("/api/compras-agiles?" + parametros, { signal: control.signal })
        .then(r => { setDatos(r); setError(""); })
        .catch(e => { if (!control.signal.aborted) setError(e.message); })
        .finally(() => { if (!control.signal.aborted) setCargando(false); });
    }, 250);
    return () => { clearTimeout(espera); control.abort(); };
  }, [q, region, soloAbiertas, offset, version]);
  return <>
    <div className="filtros ca-filtros">
      <label>Región del comprador<input value={region} placeholder="Ej.: Metropolitana" onChange={e => setRegion(e.target.value)} /></label>
      <label><input type="checkbox" checked={soloAbiertas} onChange={e => setSoloAbiertas(e.target.checked)} /> Solo abiertas</label>
      <span aria-live="polite">{datos.total} {datos.total === 1 ? "resultado" : "resultados"}</span>
    </div>
    <div className="scroll" aria-busy={cargando}><table className="ca-tabla">
      <colgroup><col style={{ width: 185 }} /><col /><col style={{ width: "22%" }} /><col style={{ width: 150 }} /><col style={{ width: 150 }} /></colgroup>
      <thead><tr><th>Código</th><th>Compra Ágil</th><th>Institución</th><th>Presupuesto</th><th>Preselección</th></tr></thead>
      <tbody>{datos.items.map(c => {
        const aviso = plazo(c.fecha_cierre);
        const estado = c.clasificacion || "pendiente_evaluacion";
        return <tr key={c.id} onClick={() => abrirCompraAgil(c.id)}
          className={c.clientes_importantes?.length ? "opportunity-important" : undefined}>
          <td><button className="cod" onClick={e => { e.stopPropagation(); abrirCompraAgil(c.id); }}>{c.codigo_externo}</button>
            {c.url_oficial && <div className="sub"><a href={c.url_oficial} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>Mercado Público ↗</a></div>}</td>
          <td className="nom"><TituloLicitacion as="div" licitacion={c} /></td>
          <td title={c.nombre_organismo}><span className="cut">{c.nombre_unidad || c.nombre_organismo || "-"}</span>
            <div className="sub cut">{c.region_comprador}</div><ClienteImportanteBadge clientes={c.clientes_importantes} /></td>
          <td>{c.monto_disponible == null ? "-" : dinero(c.monto_disponible, c.moneda)}
            <div className="sub">cierra {fecha(c.fecha_cierre)}</div>{aviso && <span className="ca-plazo" data-nivel={aviso.nivel}>{aviso.texto}</span>}</td>
          <td><span className={"badge " + (TONOS[estado] || "")}>{ETIQUETAS[estado]}</span></td>
        </tr>;
      })}</tbody>
    </table>
    {error ? <div className="msg err" role="alert">No se pudieron cargar las Compras Ágiles. {error}</div>
      : cargando ? <p className="msg">Cargando Compras Ágiles…</p> : !datos.items.length ? <p className="msg">Sin Compras Ágiles para esta búsqueda.</p> : null}</div>
    {datos.total > LIMITE && <div className="card-head ca-paginas">
      <span>{offset + 1}–{Math.min(offset + LIMITE, datos.total)} de {datos.total}</span>
      <div><button disabled={cargando || offset === 0} onClick={() => setOffset(o => o - LIMITE)}>Anterior</button>{" "}
        <button disabled={cargando || offset + LIMITE >= datos.total} onClick={() => setOffset(o => o + LIMITE)}>Siguiente</button></div>
    </div>}
  </>;
}
