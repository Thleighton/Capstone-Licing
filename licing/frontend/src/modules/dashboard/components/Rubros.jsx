import { rubros } from "../../../core/data/licitaciones";

export default function Rubros({ rows }) {
  const data = rubros(rows), max = Math.max(1, ...data.map(d => d[1]));
  return data.map(([n, c]) => (
    <div className="rubro" key={n}>
      <div className="row"><b>{n}</b><span>{c} licitaciones</span></div>
      <div className="bar"><i style={{ width: Math.round(c / max * 100) + "%" }} /></div>
    </div>
  ));
}
