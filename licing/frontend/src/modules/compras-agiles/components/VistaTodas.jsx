import { useEffect, useState } from "react";
import { apiJson } from "../../../core/api/client";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import CierrePlazo from "../../../core/ui/CierrePlazo";
import { dinero } from "../../../core/ui/format";
import { abrirCompraAgil } from "../store";
import { ETIQUETAS, TONOS } from "../comun";
import PreseleccionControles from "../../../core/ui/PreseleccionControles";
import EstadoPlazo from "../../../core/ui/EstadoPlazo";
import PaginacionResultados from "../../../core/ui/PaginacionResultados";

const LIMITE = 50;

// Todas las Compras Ágiles guardadas por Core, con búsqueda y filtros en el servidor.
export default function VistaTodas({ q, codigo, onCodigo, version, ordenCierre, ordenPublicacion, onOrdenCierre, onOrdenPublicacion, onClasificacion }) {
  const [offset, setOffset] = useState(0);
  const [datos, setDatos] = useState({ items: [], total: 0 });
  const [cargando, setCargando] = useState(true), [error, setError] = useState("");
  useEffect(() => { setOffset(0); }, [q, codigo, ordenCierre, ordenPublicacion]);
  useEffect(() => {
    const control = new AbortController();
    setCargando(true);
    const espera = setTimeout(() => {
      const parametros = new URLSearchParams({ q, codigo: (codigo || "").trim(), orden_cierre: ordenCierre, orden_publicacion: ordenPublicacion, limite: String(LIMITE), offset: String(offset) });
      apiJson("/api/compras-agiles?" + parametros, { signal: control.signal })
        .then(r => { setDatos(r); setError(""); })
        .catch(e => { if (!control.signal.aborted) setError(e.message); })
        .finally(() => { if (!control.signal.aborted) setCargando(false); });
    }, 250);
    return () => { clearTimeout(espera); control.abort(); };
  }, [q, codigo, ordenCierre, ordenPublicacion, offset, version]);
  return <>
    <PreseleccionControles clasificacion="" ordenCierre={ordenCierre} ordenPublicacion={ordenPublicacion}
      onOrdenCierre={onOrdenCierre} onOrdenPublicacion={onOrdenPublicacion} total={datos.total}
      onClasificacion={onClasificacion} entidad="Compras Ágiles" mostrarBusquedaId busquedaId={codigo || ""}
      onBusquedaId={onCodigo} textoBusquedaId="Ej. 1195-539-COT26" ariaBusquedaId="Buscar por ID de Compra Ágil" />
    <div className="scroll" aria-busy={cargando}><table className="ca-tabla">
      <colgroup><col style={{ width: 185 }} /><col /><col style={{ width: "22%" }} /><col style={{ width: 150 }} /><col style={{ width: 150 }} /></colgroup>
      <thead><tr><th>Código</th><th>Compra Ágil</th><th>Institución</th><th>Presupuesto</th><th>Preselección</th></tr></thead>
      <tbody>{datos.items.map(c => {
        const estado = c.clasificacion || "pendiente_evaluacion";
        return <tr key={c.id} onClick={() => abrirCompraAgil(c.id)}
          className={c.clientes_importantes?.length ? "opportunity-important" : undefined}>
          <td><span className="ca-codigo-estado"><button className="cod" onClick={e => { e.stopPropagation(); abrirCompraAgil(c.id); }}>{c.codigo_externo}</button><EstadoPlazo fila={c} /></span>
            {c.url_oficial && <div className="sub"><a href={c.url_oficial} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>Mercado Público ↗</a></div>}</td>
          <td className="nom"><TituloLicitacion as="div" licitacion={c} /></td>
          <td title={c.nombre_organismo}><span className="cut">{c.nombre_unidad || c.nombre_organismo || "-"}</span>
            <div className="sub cut">{c.region_comprador}</div><ClienteImportanteBadge clientes={c.clientes_importantes} /></td>
          <td>{c.monto_disponible == null ? "-" : dinero(c.monto_disponible, c.moneda)}
            <CierrePlazo fechaCierre={c.fecha_cierre} compacto /></td>
          <td><span className={"badge " + (TONOS[estado] || "")}>{ETIQUETAS[estado]}</span></td>
        </tr>;
      })}</tbody>
    </table>
    {error ? <div className="msg err" role="alert">No se pudieron cargar las Compras Ágiles. {error}</div>
      : cargando ? <p className="msg">Cargando Compras Ágiles…</p> : !datos.items.length ? <p className="msg">Sin Compras Ágiles para esta búsqueda.</p> : null}</div>
    {datos.total > 0 && <PaginacionResultados total={datos.total} offset={offset}
      limite={LIMITE} cargando={cargando} onCambiar={setOffset} etiqueta="Páginas de Compras Ágiles" />}
  </>;
}
