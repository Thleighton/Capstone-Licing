import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import { dinero, fechaCorta } from "../../core/ui/format";
import EstadoBadge from "./components/EstadoBadge";
export default function OportunidadesPage() {
  const { rows, total, filtros, setFiltros, abrirFicha, error, cargando, pagina, setPagina, limite } = useLicitaciones();
  return <>
    <div className="overview-note">Consulta las licitaciones guardadas, busca por nombre o institución y abre su detalle.</div>
    <section className="card">
      <div className="card-head"><h2>Explorar oportunidades</h2><button onClick={() => setFiltros({ visibles: !filtros.visibles })}>Filtros</button></div>
      {filtros.visibles && <div className="filtros">
        <label>Región del comprador<input value={filtros.region} placeholder="Ej.: Metropolitana" onChange={e => setFiltros({ region: e.target.value })} /></label>
        <label><input type="checkbox" checked={filtros.soloAbiertas} onChange={e => setFiltros({ soloAbiertas: e.target.checked })} /> Solo abiertas</label>
      </div>}
      <div className="scroll" aria-busy={cargando}><table>
        <colgroup><col style={{ width: 140 }} /><col /><col style={{ width: "25%" }} /><col style={{ width: 130 }} /><col style={{ width: 110 }} /></colgroup>
        <thead><tr><th>ID</th><th>Nombre</th><th>Institución</th><th>Monto</th><th>Estado</th></tr></thead>
        <tbody>{!cargando && rows.map(r => <tr key={r.id} onClick={() => abrirFicha(r.id)}>
          <td><button className="cod" onClick={e => { e.stopPropagation(); abrirFicha(r.id); }}>{r.codigo_externo}</button><div className="sub">Licitación</div></td>
          <td className="nom cut" title={r.nombre}>{r.nombre || "Sin nombre"}</td>
          <td className="cut" title={r.nombre_organismo}>{r.nombre_unidad || r.nombre_organismo || "-"}<div className="sub cut">{r.region_comprador}</div></td>
          <td>{dinero(r.monto_estimado, r.moneda)}<div className="sub">cierra {fechaCorta(r.fecha_cierre)}</div></td>
          <td><EstadoBadge r={r} /></td>
        </tr>)}</tbody>
      </table>
      {error ? <div className="msg err" role="alert">{error}</div> : cargando ? <p className="msg">Cargando licitaciones…</p> : !rows.length ? <p className="msg">Sin licitaciones para esta búsqueda.</p> : null}</div>
      <div className="card-head"><span aria-live="polite">{total ? (pagina * limite + 1) + "–" + Math.min((pagina + 1) * limite, total) + " de " + total : "0 resultados"}</span>
        <div><button disabled={cargando || pagina === 0} onClick={() => setPagina(p => p - 1)}>Anterior</button>{" "}
          <button disabled={cargando || (pagina + 1) * limite >= total} onClick={() => setPagina(p => p + 1)}>Siguiente</button></div>
      </div>
    </section>
  </>;
}
