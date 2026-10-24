export default function Estados({ datos }) {
  const max = Math.max(1, ...datos.map(d => d.cantidad));
  if (!datos.length) return <p className="empty">Sin licitaciones guardadas.</p>;
  return datos.map((d, index) => <div className="rubro" key={d.estado} style={{ "--state-color": /publicada|activa/i.test(d.estado) ? "var(--accent)" : ["var(--violet)", "var(--blue)", "var(--warn-ring)", "var(--err)"][index % 4] }}>
    <div className="row"><b>{d.estado}</b><span>{d.cantidad} licitaciones</span></div>
    <div className="bar"><i style={{ width: Math.round(d.cantidad / max * 100) + "%" }} /></div>
  </div>);
}
