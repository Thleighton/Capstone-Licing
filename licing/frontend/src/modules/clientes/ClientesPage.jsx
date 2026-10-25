import { useEffect, useState } from "react";
import { apiJson } from "../../core/api/client";
import ClienteImportanteBadge from "../../core/ui/ClienteImportanteBadge";
import AgregarClienteDemo from "./AgregarClienteDemo";
import Icon from "../../core/ui/Icon";
import "./clientes.css";

export default function ClientesPage() {
  const [clientes, setClientes] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const [clientesDemo, setClientesDemo] = useState([]);
  const [agregando, setAgregando] = useState(false);
  const [mensaje, setMensaje] = useState("");
  function agregarCliente(datos) {
    setClientesDemo(previos => [...previos, { ...datos, id: crypto.randomUUID() }]);
    setAgregando(false);
    setMensaje("Cliente agregado a la demostración.");
  }
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
      <div className="clientes-toolbar-actions">
        {!cargando && !error && <span className="badge violet">{clientes.length} organismos</span>}
        <button type="button" className="primary" onClick={() => { setMensaje(""); setAgregando(true); }}><Icon name="plus" />Agregar cliente</button>
      </div>
    </section>
    {cargando ? <p role="status">Cargando clientes importantes…</p> : error ? <div className="msg err" role="alert">{error} <button onClick={() => setVersion(v => v + 1)}>Reintentar</button></div> :
      <div className="important-clients-grid">{clientes.map(c => <article className="card panel important-client-card" key={c.id}>
        <ClienteImportanteBadge clientes={[c]} mostrarNombre={false} />
        <h3>{c.nombre}</h3>
        <p>{c.alcance}</p>
      </article>)}</div>}
    {mensaje && <p className="clientes-demo-status" role="status">{mensaje}</p>}
    {!!clientesDemo.length && <section className="clientes-demo-section" aria-labelledby="clientes-demo-titulo">
      <div className="section-title"><h2 id="clientes-demo-titulo">Clientes agregados</h2><span className="badge blue">Demo · {clientesDemo.length}</span></div>
      <p className="sub">Esta lista se conserva mientras navegas y se borra al recargar la página.</p>
      <div className="important-clients-grid">{clientesDemo.map(c => <article className="card panel cliente-demo-card" key={c.id}>
        <div className="cliente-demo-card-top"><span className="badge blue">Demo</span><button type="button" aria-label={`Quitar cliente demo ${c.nombre}`}
          onClick={() => { setClientesDemo(previos => previos.filter(p => p.id !== c.id)); setMensaje("Cliente retirado de la demostración."); }}>Quitar</button></div>
        <h3>{c.nombre}</h3>
        {(c.contacto || c.correo || c.telefono) && <dl className="cliente-demo-contacto">
          {c.contacto && <div><dt>Contacto</dt><dd>{c.contacto}</dd></div>}
          {c.correo && <div><dt>Correo</dt><dd>{c.correo}</dd></div>}
          {c.telefono && <div><dt>Teléfono</dt><dd>{c.telefono}</dd></div>}
        </dl>}
        {!!c.servicios.length && <div className="cliente-demo-tags" aria-label="Servicios de interés">{c.servicios.map(s => <span className="badge" key={s}>{s}</span>)}</div>}
      </article>)}</div>
    </section>}
    <AgregarClienteDemo abierto={agregando} onCerrar={() => setAgregando(false)} onAgregar={agregarCliente}
      nombresExistentes={[...clientes, ...clientesDemo].map(c => c.nombre)} />
  </>;
}
