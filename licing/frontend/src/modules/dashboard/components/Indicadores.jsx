import { esCandidata, esNueva } from "../../../core/data/licitaciones";
import { DIA } from "../../../core/ui/format";
import Icon from "../../../core/ui/Icon";

function Stat({ n, titulo, icono, nota }) {
  return (
    <div className="stat">
      <div className="top">{titulo}<span className="ico"><Icon name={icono} /></span></div>
      <div className="bottom"><b>{n}</b><small>{nota}</small></div>
    </div>
  );
}

export default function Indicadores({ rows, total }) {
  const cand = rows.filter(esCandidata);
  const pronto = cand.filter(r => r.fecha_cierre && new Date(r.fecha_cierre) - Date.now() > 0 && new Date(r.fecha_cierre) - Date.now() < 3 * DIA).length;
  return (
    <section className="stats">
      <Stat n={rows.filter(esNueva).length} titulo="Nuevas hoy" icono="plus" nota="últimas 24 h" />
      <Stat n={cand.length} titulo="Relevantes" icono="star" nota={"de " + total + " totales"} />
      <Stat n={pronto} titulo="Cierran pronto" icono="alert" nota="en 3 días o menos" />
      <Stat n={rows.filter(r => r.requisito_extraido?.length).length} titulo="Analizadas" icono="chart" nota="con requisitos extraídos" />
    </section>
  );
}
