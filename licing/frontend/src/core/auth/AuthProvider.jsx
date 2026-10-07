// Contexto de autenticación: expone el perfil del usuario y las acciones de acceso.
// Cualquier módulo puede usar `useAuth()` para saber quién está conectado.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { cargarConfig } from "../api/config";
import { setOnSinSesion } from "../api/client";
import {
  auth, cargarPerfil, capturarHashAuth, guardarSesion, leerSesion, normSesion, sesionActual, tokenVigente,
} from "./session";

// Se evalúa una sola vez al cargar la app (antes de que el router toque el hash).
const hashAuth = capturarHashAuth();

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [estado, setEstado] = useState("cargando"); // cargando | login | listo
  const [perfil, setPerfil] = useState(null);
  const [modo, setModo] = useState("login");         // login | recuperar | nueva
  const [hint, setHint] = useState("");
  const [mensaje, setMensaje] = useState({ texto: "", ok: false });
  const [configured, setConfigured] = useState(true);

  const mostrarLogin = useCallback((texto = "", nuevoModo = "login", nuevoHint = "") => {
    setPerfil(null);
    setModo(nuevoModo);
    setHint(nuevoHint);
    setMensaje({ texto, ok: false });
    setEstado("login");
  }, []);

  const entrar = useCallback(async () => {
    const token = await tokenVigente();
    if (!token) return mostrarLogin("Tu sesión expiró. Vuelve a ingresar.");
    let p;
    try { p = await cargarPerfil(token); } catch (e) { return mostrarLogin(e.message); }
    if (!p || !p.activo) {
      guardarSesion(null);
      return mostrarLogin(!p ? "Tu usuario no tiene perfil en LICING. Contacta al administrador."
                             : "Tu cuenta está desactivada. Contacta al administrador.");
    }
    setPerfil(p);
    setMensaje({ texto: "", ok: false });
    setEstado("listo");
  }, [mostrarLogin]);

  // Arranque: leer configuración y retomar sesión si existe.
  useEffect(() => {
    setOnSinSesion((m, expirada) => { if (expirada) guardarSesion(null); mostrarLogin(m); });
    (async () => {
      const cfg = await cargarConfig();
      setConfigured(cfg.configured);
      if (!cfg.configured) {
        return mostrarLogin("Falta configurar USUARIOS_URL y USUARIOS_ANON_KEY en el .env (o en las variables de entorno de Vercel).");
      }
      if (hashAuth?.error) return mostrarLogin(hashAuth.error);
      if (hashAuth && (hashAuth.tipo === "invite" || hashAuth.tipo === "recovery")) {
        return mostrarLogin("", "nueva", hashAuth.tipo === "invite"
          ? "Bienvenido/a. Define la contraseña con la que entrarás a LICING."
          : "Escribe tu nueva contraseña.");
      }
      if (!hashAuth) leerSesion();
      if (sesionActual()) return entrar();
      mostrarLogin();
    })();
  }, [entrar, mostrarLogin]);

  // Mantener la clase del <body> que usa el CSS para mostrar login o app.
  useEffect(() => {
    document.body.classList.toggle("locked", estado !== "listo");
  }, [estado]);

  const acciones = {
    async login(email, pass) {
      guardarSesion(normSesion(await auth("token?grant_type=password", { body: { email, password: pass } })));
      await entrar();
    },
    async recuperar(email) {
      await auth("recover?redirect_to=" + encodeURIComponent(location.origin + location.pathname), { body: { email } });
      setModo("login");
      setMensaje({ texto: "Si el correo está registrado, te llegará un enlace para crear una nueva contraseña.", ok: true });
    },
    async nuevaPassword(pass) {
      await auth("user", { method: "PUT", body: { password: pass }, token: await tokenVigente() });
      await entrar();
    },
    async logout() {
      const token = sesionActual()?.access_token;
      guardarSesion(null);
      if (token) await auth("logout", { token }).catch(() => {});
      history.replaceState(null, "", location.pathname);
      location.reload();
    },
  };

  const value = { estado, perfil, modo, setModo, hint, setHint, mensaje, setMensaje, configured, ...acciones };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
