import { useEffect, useId, useState } from "react";
import { fecha } from "../../../core/ui/format";
import { officialOpportunityUrl } from "../../oportunidades/utils";
import Icon from "../../../core/ui/Icon";
import ClienteImportanteBadge from "../../../core/ui/ClienteImportanteBadge";
import TituloLicitacion from "../../../core/ui/TituloLicitacion";
import "./proximas-a-cerrar.css";

const pestañas = [
  { estado: "preseleccionada", nombre: "Posibles oportunidades" },
  { estado: "revision_manual", nombre: "Pendientes de revisión" },
];

export default function ProximasACerrar({ rows, disponibles = true, estado, abrirFicha, mostrarFicha = true }) {
  const [pestaña, setPestaña] = useState("preseleccionada");
  const [ahora, setAhora] = useState(Date.now);
  const id = useId();
  useEffect(() => {
    const reloj = setInterval(() => setAhora(Date.now()), 60000);
    return () => clearInterval(reloj);
  }, []);
  if (estado === "err") return <p className="empty">No se pudieron cargar los datos. Pulsa Actualizar para volver a intentar.</p>;
  if (estado !== "ok") return <p className="empty">Cargando oportunidades…</p>;
  if (!disponibles) return <p className="empty">No se pudo consultar la preselección. Pulsa Actualizar para volver a intentar.</p>;
  const next = rows.filter(r => r.estado_seleccion === pestaña)
    .sort((a, b) => new Date(a.fecha_cierre) - new Date(b.fecha_cierre) || a.id - b.id);
  function moverPestaña(e, indice) {
    const destino = e.key === "Home" ? 0 : e.key === "End" ? pestañas.length - 1
      : e.key === "ArrowRight" ? (indice + 1) % pestañas.length
        : e.key === "ArrowLeft" ? (indice + pestañas.length - 1) % pestañas.length : null;
    if (destino === null) return;
    e.preventDefault();
    setPestaña(pestañas[destino].estado);
    document.getElementById(`${id}-${pestañas[destino].estado}`)?.focus();
  }
  return <div className="closing-opportunities">
    <div className="closing-tabs" role="tablist" aria-label="Clasificación de próximos cierres">{pestañas.map((p, i) => <button
      key={p.estado} id={`${id}-${p.estado}`} type="button" role="tab" aria-selected={pestaña === p.estado}
      aria-controls={`${id}-contenido`} tabIndex={pestaña === p.estado ? 0 : -1}
      onClick={() => setPestaña(p.estado)} onKeyDown={e => moverPestaña(e, i)}>
      <span className="closing-tab-label">{p.nombre}</span><span className="closing-count">{rows.filter(r => r.estado_seleccion === p.estado).length}</span>
    </button>)}</div>
    <div className="closing-list" id={`${id}-contenido`} role="tabpanel" aria-labelledby={`${id}-${pestaña}`} tabIndex={0}>
      {!next.length && <p className="empty">{pestaña === "preseleccionada" ? "No hay posibles oportunidades con cierre pendiente." : "No hay licitaciones pendientes de revisión con cierre pendiente."}</p>}
      {next.map(r => {
        const restantes = new Date(r.fecha_cierre).getTime() - ahora;
        const dia = 24 * 60 * 60 * 1000;
        const aviso = restantes <= 4 * dia;
        const nivel = restantes <= dia ? "critical" : "warning";
        const unidad = restantes <= 3600000 ? "min" : restantes <= dia ? "h" : "días";
        const cantidad = Math.max(1, Math.ceil(restantes / (unidad === "min" ? 60000 : unidad === "h" ? 3600000 : dia)));
        const mensaje = restantes <= 0 ? "Plazo vencido" : `${cantidad === 1 ? "Queda" : "Quedan"} ${cantidad} ${unidad}`;
        return <article className="closing-item" data-urgency={aviso ? nivel : undefined} data-cliente-importante={!!r.clientes_importantes?.length} key={r.id}>
          <div className="closing-item-header">
            {officialOpportunityUrl(r) ? <a className="closing-reference" href={officialOpportunityUrl(r)} target="_blank" rel="noopener noreferrer" aria-label={`Ver licitación ${r.codigo_externo} en Mercado Público`}>{r.codigo_externo} ↗</a> : <span className="closing-reference">{r.codigo_externo}</span>}
            {aviso && <span className={"closing-alert closing-alert-" + nivel}><Icon name="clock" />{mensaje}</span>}
          </div>
          <ClienteImportanteBadge clientes={r.clientes_importantes} />
          <TituloLicitacion licitacion={r} className="closing-item-title" />
          <div className="closing-item-footer">
            <time dateTime={r.fecha_cierre}><span>Cierre</span>{fecha(r.fecha_cierre)}</time>
            {mostrarFicha && <button type="button" onClick={() => abrirFicha(r.id)}>Ver ficha</button>}
          </div>
        </article>;
      })}
    </div>
    {next.length > 3 && <p className="closing-scroll-note">{next.length} licitaciones · Desplázate para verlas todas.</p>}
  </div>;
}

