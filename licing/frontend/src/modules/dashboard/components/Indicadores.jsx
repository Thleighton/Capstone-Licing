import Icon from "../../../core/ui/Icon";

function Stat({ n, titulo, icono, nota, tono }) {
  return (
    <div className={"stat stat-" + tono}>
      <div className="top">{titulo}<span className="ico"><Icon name={icono} /></span></div>
      <div className="bottom"><b>{n}</b><small>{nota}</small></div>
    </div>
  );
}

export default function Indicadores({ resumen }) {
  return (
    <section className="stats">
      <Stat n={resumen.nuevas} titulo="Incorporadas hoy" icono="plus" nota="Últimas 24 horas" tono="violet" />
      <Stat n={resumen.abiertas} titulo="Abiertas" icono="star" nota="Según el último detalle guardado" tono="teal" />
      <Stat n={resumen.cierran_pronto} titulo="Cierran pronto" icono="clock" nota="En 3 días o menos" tono="amber" />
      <Stat n={resumen.total} titulo="Guardadas" icono="briefcase" nota="Total de licitaciones" tono="blue" />
    </section>
  );
}
