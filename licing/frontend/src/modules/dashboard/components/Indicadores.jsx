import Icon from "../../../core/ui/Icon";

function Stat({ n, titulo, icono, nota }) {
  return (
    <div className="stat">
      <div className="top">{titulo}<span className="ico"><Icon name={icono} /></span></div>
      <div className="bottom"><b>{n}</b><small>{nota}</small></div>
    </div>
  );
}

export default function Indicadores({ resumen }) {
  return (
    <section className="stats">
      <Stat n={resumen.nuevas} titulo="Incorporadas hoy" icono="plus" nota="últimas 24 h" />
      <Stat n={resumen.abiertas} titulo="Abiertas" icono="star" nota="según el último detalle guardado" />
      <Stat n={resumen.cierran_pronto} titulo="Cierran pronto" icono="alert" nota="en 3 días o menos" />
      <Stat n={resumen.total} titulo="Guardadas" icono="chart" nota="total de licitaciones" />
    </section>
  );
}
