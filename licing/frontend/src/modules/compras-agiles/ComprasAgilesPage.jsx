import { useEffect, useId, useState } from "react";
import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import Icon from "../../core/ui/Icon";
import VistaPreseleccion from "./components/VistaPreseleccion";
import VistaTodas from "./components/VistaTodas";
import { useResumenComprasAgiles } from "./comun";
import "./compras-agiles.css";

const VISTAS = [
  { id: "hotel", nombre: "Para el hotel" },
  { id: "todas", nombre: "Todas" },
];

function Stat({ n, titulo, icono, nota }) {
  return <div className="stat">
    <div className="top">{titulo}<span className="ico"><Icon name={icono} /></span></div>
    <div className="bottom"><b>{n ?? "–"}</b><small>{nota}</small></div>
  </div>;
}

export default function ComprasAgilesPage() {
  // Refrescar los datos compartidos recarga también esta página.
  const { actualizado } = useLicitaciones();
  const { resumen, error } = useResumenComprasAgiles(actualizado);
  const [vista, setVista] = useState("hotel");
  const [texto, setTexto] = useState(""), [q, setQ] = useState("");
  const id = useId();
  useEffect(() => {
    const espera = setTimeout(() => setQ(texto.trim()), 300);
    return () => clearTimeout(espera);
  }, [texto]);
  function mover(e, indice) {
    const destino = e.key === "ArrowRight" || e.key === "ArrowLeft" ? (indice + 1) % VISTAS.length : null;
    if (destino === null) return;
    e.preventDefault();
    setVista(VISTAS[destino].id);
    document.getElementById(`${id}-${VISTAS[destino].id}`)?.focus();
  }
  const pre = resumen?.preseleccion;
  return <div className="ca-page">
    <p className="overview-note">Cotizaciones de Compra Ágil publicadas en Mercado Público. Se cargan en cada turno de ingesta y pasan por los mismos tres pilares que las licitaciones: vigencia, lugar en la RM y servicio solicitado.</p>
    {error && <div className="msg err" role="alert">No se pudo actualizar el resumen. {error}</div>}
    {resumen && !resumen.carga_inicial_completa && <p className="ca-aviso" role="status"><Icon name="clock" />Carga inicial en curso: las Compras Ágiles abiertas se incorporan de a poco en cada turno.</p>}
    <section className="stats" aria-label="Indicadores de Compras Ágiles">
      <Stat n={resumen?.nuevas} titulo="Incorporadas hoy" icono="plus" nota="Últimas 24 horas" />
      <Stat n={resumen?.abiertas} titulo="Abiertas" icono="bolt" nota={resumen ? `${resumen.total} guardadas` : "Cargando…"} />
      <Stat n={resumen?.cierran_pronto} titulo="Cierran en 24 h" icono="clock" nota="Abiertas con cierre próximo" />
      <Stat n={pre?.preseleccionada} titulo="Posibles oportunidades" icono="star" nota={pre ? `${pre.revision_manual} en revisión` : "Cargando…"} />
    </section>
    <section className="card">
      <div className="card-head ca-toolbar">
        <div className="ca-tabs" role="tablist" aria-label="Vistas de Compras Ágiles">{VISTAS.map((v, i) => <button
          key={v.id} id={`${id}-${v.id}`} type="button" role="tab" aria-selected={vista === v.id}
          aria-controls={`${id}-panel`} tabIndex={vista === v.id ? 0 : -1}
          onClick={() => setVista(v.id)} onKeyDown={e => mover(e, i)}>{v.nombre}</button>)}</div>
        <label className="search ca-search"><Icon name="search" />
          <input type="search" value={texto} onChange={e => setTexto(e.target.value)}
            placeholder={vista === "hotel" ? "Buscar por nombre o código…" : "Buscar por nombre, código o institución…"}
            aria-label="Buscar Compras Ágiles" /></label>
      </div>
      <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${vista}`}>
        {vista === "hotel" ? <VistaPreseleccion q={q} version={actualizado} /> : <VistaTodas q={q} version={actualizado} />}
      </div>
    </section>
  </div>;
}
