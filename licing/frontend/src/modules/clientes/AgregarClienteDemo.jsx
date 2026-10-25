import { useEffect, useId, useRef, useState } from "react";
import Dialog from "../../core/ui/Dialog";

const VACIO = { nombre: "", contacto: "", correo: "", telefono: "", servicios: [] };
const SERVICIOS = ["Alojamiento", "Salones", "Alimentación"];

export default function AgregarClienteDemo({ abierto, nombresExistentes, onCerrar, onAgregar }) {
  const id = useId();
  const nombreRef = useRef(null);
  const [datos, setDatos] = useState(VACIO);
  const [error, setError] = useState("");
  useEffect(() => {
    if (abierto) { setDatos(VACIO); setError(""); nombreRef.current?.focus(); }
  }, [abierto]);
  function cerrar() { setDatos(VACIO); setError(""); onCerrar(); }
  const cambiar = campo => e => { setDatos(d => ({ ...d, [campo]: e.target.value })); setError(""); };
  function guardar(e) {
    e.preventDefault();
    const nombre = datos.nombre.trim();
    if (!nombre) { setError("Escribe el nombre del cliente o institución."); nombreRef.current?.focus(); return; }
    if (nombresExistentes.some(n => n.localeCompare(nombre, "es", { sensitivity: "base" }) === 0)) {
      setError("Ya hay un cliente con ese nombre."); nombreRef.current?.focus(); return;
    }
    onAgregar({ ...datos, nombre, contacto: datos.contacto.trim(), correo: datos.correo.trim(), telefono: datos.telefono.trim() });
    setDatos(VACIO); setError("");
  }
  return <Dialog open={abierto} onClose={cerrar} className="cliente-demo-dialog" aria-labelledby={`${id}-titulo`} aria-describedby={`${id}-ayuda`}>
    <header className="dlg-head"><div><span className="badge blue">Demo</span><h2 id={`${id}-titulo`}>Agregar cliente</h2></div>
      <button type="button" onClick={cerrar} aria-label="Cerrar formulario de cliente">Cerrar</button></header>
    <form onSubmit={guardar} className="cliente-demo-form">
      <div className="dlg-body">
        <p id={`${id}-ayuda`} className="cliente-demo-help">El cliente se agregará a esta demostración. Los datos se borran al recargar la página.</p>
        <div className="fields">
          <label className="wide">Nombre del cliente o institución *<input ref={nombreRef} autoFocus required maxLength={120}
            value={datos.nombre} onChange={cambiar("nombre")} placeholder="Ej.: Corporación de Turismo" /></label>
          <label className="wide">Persona de contacto<input maxLength={100} value={datos.contacto} onChange={cambiar("contacto")} placeholder="Nombre y apellido" /></label>
          <label>Correo electrónico<input type="email" maxLength={160} value={datos.correo} onChange={cambiar("correo")} placeholder="contacto@ejemplo.cl" /></label>
          <label>Teléfono<input type="tel" maxLength={30} value={datos.telefono} onChange={cambiar("telefono")} placeholder="+56 9 1234 5678" /></label>
        </div>
        <fieldset className="cliente-demo-services"><legend>Servicios de interés (opcional)</legend>
          <div className="cliente-demo-checks">{SERVICIOS.map(s => <label key={s}><input type="checkbox" checked={datos.servicios.includes(s)}
            onChange={e => setDatos(d => ({ ...d, servicios: e.target.checked ? [...d.servicios, s] : d.servicios.filter(v => v !== s) }))} />{s}</label>)}</div>
        </fieldset>
        {error && <p className="msg err" role="alert">{error}</p>}
      </div>
      <footer className="cliente-demo-actions"><button type="button" onClick={cerrar}>Cancelar</button><button type="submit" className="primary">Agregar cliente demo</button></footer>
    </form>
  </Dialog>;
}
