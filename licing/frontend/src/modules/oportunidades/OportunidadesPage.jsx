import { useMemo } from "react";
import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import { confianza, esCandidata } from "../../core/data/licitaciones";
import { clp, fechaCorta } from "../../core/ui/format";
import Anillo from "./components/Anillo";
import EstadoBadge from "./components/EstadoBadge";
import { tipoLegible } from "./utils";

const LIMITE = 100;

export default function OportunidadesPage() {
  const { rows, q, filtros, setFiltros, abrirFicha, error, cargando } = useLicitaciones();

  const lista = useMemo(() => {
    const texto = q.trim().toLowerCase(), ahora = Date.now();
    const orden = r => (esCandidata(r) ? 0 : 4) + (r.fecha_cierre && new Date(r.fecha_cierre) >= ahora ? 0 : 2);
    return rows
      .filter(r => (!filtros.soloValidas || esCandidata(r)) && (!filtros.tipo || r.tipo === filtros.tipo) &&
        (!texto || [r.codigo_mp, r.nombre, r.organismo?.nombre, r.organismo?.unidad_compra].some(v => (v || "").toLowerCase().includes(texto))))
      .sort((a, b) => orden(a) - orden(b) || (new Date(a.fecha_cierre || 8.64e15) - new Date(b.fecha_cierre || 8.64e15)));
  }, [rows, q, filtros]);

  let msg = "";
  if (error) msg = error;
  else if (cargando) msg = "";
  else if (!lista.length) msg = rows.length ? "Sin resultados para el filtro." : "Conectado, pero aún no hay licitaciones cargadas.";
  else if (lista.length > LIMITE) msg = "Mostrando " + LIMITE + " de " + lista.length + ". Usa el buscador o los filtros.";

  return (
    <>
      <div className="overview-note">Consulta las oportunidades, busca por nombre o institución y abre una ficha para ver su detalle.</div>
      <section className="card">
        <div className="card-head"><h2>Explorar oportunidades</h2>
          <button onClick={() => setFiltros({ visibles: !filtros.visibles })}>Filtros</button></div>
        {filtros.visibles && (
          <div className="filtros">
            <label>Tipo
              <select id="fTipo" value={filtros.tipo} onChange={e => setFiltros({ tipo: e.target.value })}>
                <option value="">Todos</option><option value="licitacion">Licitación</option>
                <option value="compra_agil">Compra ágil</option><option value="otro">Otro</option>
              </select></label>
            <label><input type="checkbox" checked={filtros.soloValidas} onChange={e => setFiltros({ soloValidas: e.target.checked })} /> Solo las que pasan el pre-filtro</label>
          </div>
        )}
        <div className="scroll">
          <table>
            <colgroup><col style={{ width: 140 }} /><col /><col style={{ width: "20%" }} /><col style={{ width: 105 }} /><col style={{ width: 64 }} /><col style={{ width: 96 }} /></colgroup>
            <thead><tr><th>ID</th><th>Nombre</th><th>Institución</th><th>Monto</th><th title="Confianza del análisis automático de requisitos">Análisis</th><th>Estado</th></tr></thead>
            <tbody>
              {lista.slice(0, LIMITE).map(r => (
                <tr key={r.id} onClick={() => abrirFicha(r.id)}>
                  <td><a className="cod" href="#oportunidades" onClick={e => e.preventDefault()}>{r.codigo_mp}</a><div className="sub">{tipoLegible(r.tipo)}</div></td>
                  <td className="nom cut" title={r.nombre}>{r.nombre}</td>
                  <td className="cut" title={r.organismo?.nombre}>{r.organismo?.unidad_compra || r.organismo?.nombre || "-"}<div className="sub cut">{r.organismo?.region}</div></td>
                  <td>{clp(r.monto_estimado)}<div className="sub">cierra {fechaCorta(r.fecha_cierre)}</div></td>
                  <td><Anillo valor={confianza(r)} /></td>
                  <td><EstadoBadge r={r} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {msg && <div className={"msg" + (error ? " err" : "")}>{msg}</div>}
        </div>
      </section>
    </>
  );
}
