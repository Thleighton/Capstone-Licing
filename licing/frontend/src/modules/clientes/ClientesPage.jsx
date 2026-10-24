import { useEffect, useState } from "react";
import { apiJson } from "../../core/api/client";
import ClienteImportanteBadge from "../../core/ui/ClienteImportanteBadge";

export default function ClientesPage() {
  const [clientes, setClientes] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let vigente = true;
    setCargando(true); setError("");
    apiJson("/api/clientes").then(r => { if (vigente) setClientes(r.clientes); })
      .catch(e => { if (vigente) setError(e.message); })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [version]);
  return <>
    <section className="card panel important-clients-intro">
      <div><h2>Clientes importantes para el hotel</h2>
        <p>Estos organismos tienen importancia comercial para el hotel. Sus licitaciones se destacan con una estrella y color violeta para facilitar su identificación.</p>
        <p className="sub">La marca indica importancia comercial. La clasificación sigue dependiendo de vigencia, ubicación y servicio solicitado.</p></div>
      {!cargando && !error && <span className="badge violet">{clientes.length} organismos</span>}
    </section>
    {cargando ? <p role="status">Cargando clientes importantes…</p> : error ? <div className="msg err" role="alert">{error} <button onClick={() => setVersion(v => v + 1)}>Reintentar</button></div> :
      <div className="important-clients-grid">{clientes.map(c => <article className="card panel important-client-card" key={c.id}>
        <ClienteImportanteBadge clientes={[c]} mostrarNombre={false} />
        <h3>{c.nombre}</h3>
        <p>{c.alcance}</p>
      </article>)}</div>}
  </>;
}
