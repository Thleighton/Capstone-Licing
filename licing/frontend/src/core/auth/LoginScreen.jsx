import { useEffect, useRef, useState } from "react";
import Icon from "../ui/Icon";
import { useAuth } from "./AuthProvider";

const TEXTOS = {
  login: ["Iniciar sesión", "Ingresar", "¿Olvidaste tu contraseña?"],
  recuperar: ["Recuperar contraseña", "Enviar enlace", "Volver a iniciar sesión"],
  nueva: ["Crea tu contraseña", "Guardar e ingresar", ""],
};

export default function LoginScreen() {
  const { modo, setModo, hint, setHint, mensaje, setMensaje, configured, estado, login, recuperar, nuevaPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [pass, setPass] = useState("");
  const [pass2, setPass2] = useState("");
  const [enviando, setEnviando] = useState(false);
  const emailRef = useRef(null), passRef = useRef(null);
  const [titulo, boton, enlace] = TEXTOS[modo];

  useEffect(() => { (modo === "nueva" ? passRef : emailRef).current?.focus(); }, [modo, estado]);
  useEffect(() => { if (estado === "listo") { setPass(""); setPass2(""); } }, [estado]);

  const msg = (texto, ok = false) => setMensaje({ texto, ok });

  async function onSubmit(ev) {
    ev.preventDefault();
    const correo = email.trim().toLowerCase();
    if (modo !== "nueva" && !/^\S+@\S+\.\S+$/.test(correo)) return msg("Ingresa un correo válido.");
    if (modo === "login" && !pass) return msg("Ingresa tu contraseña.");
    if (modo === "nueva") {
      if (pass.length < 8) return msg("La contraseña debe tener al menos 8 caracteres.");
      if (pass !== pass2) return msg("Las contraseñas no coinciden.");
    }
    setEnviando(true); msg("");
    try {
      if (modo === "login") await login(correo, pass);
      else if (modo === "recuperar") await recuperar(correo);
      else await nuevaPassword(pass);
    } catch (e) { msg(e.message); }
    finally { setEnviando(false); }
  }

  function cambiarModo() {
    setModo(modo === "login" ? "recuperar" : "login");
    setHint(""); msg("");
  }

  return (
    <div id="login" className="login">
      <div className="login-card">
        <div className="login-brand"><Icon name="logo" />LICING</div>
        <p className="login-sub">Asistente Inteligente de Mercado Público · Plaza San Francisco</p>
        <form onSubmit={onSubmit} noValidate>
          <h1>{titulo}</h1>
          {hint && <p className="login-hint">{hint}</p>}
          {modo !== "nueva" && (
            <label className="field">Correo
              <input ref={emailRef} type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} />
            </label>
          )}
          {modo !== "recuperar" && (
            <label className="field">{modo === "nueva" ? "Nueva contraseña" : "Contraseña"}
              <input ref={passRef} type="password" autoComplete={modo === "nueva" ? "new-password" : "current-password"} required value={pass} onChange={e => setPass(e.target.value)} />
            </label>
          )}
          {modo === "nueva" && (
            <label className="field">Repetir contraseña
              <input type="password" autoComplete="new-password" value={pass2} onChange={e => setPass2(e.target.value)} />
            </label>
          )}
          <p className={"login-msg" + (mensaje.ok ? " ok" : "")} role="alert" aria-live="polite">
            {estado === "cargando" ? "Verificando sesión..." : mensaje.texto}
          </p>
          <button type="submit" className="primary login-btn" disabled={!configured || enviando || estado === "cargando"}>{boton}</button>
          {enlace && <button type="button" className="login-link" onClick={cambiarModo}>{enlace}</button>}
        </form>
        <p className="login-foot">Acceso solo para cuentas invitadas del hotel.</p>
      </div>
    </div>
  );
}
