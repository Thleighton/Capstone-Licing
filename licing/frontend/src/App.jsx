// Ensambla la aplicación: autenticación -> datos compartidos -> layout -> módulo activo.
// Para agregar un módulo nuevo NO se toca este archivo: se registra en src/modules/index.js.
import { useEffect, useRef, useState } from "react";
import { AuthProvider, useAuth } from "./core/auth/AuthProvider";
import LoginScreen from "./core/auth/LoginScreen";
import { LicitacionesProvider } from "./core/data/LicitacionesProvider";
import Sidebar from "./core/layout/Sidebar";
import Topbar from "./core/layout/Topbar";
import PageHeading from "./core/layout/PageHeading";
import Footer from "./core/layout/Footer";
import { useHashRoute } from "./core/router/useHashRoute";
import { ThemeProvider } from "./core/ui/ThemeProvider";
import { MODULOS, MODULO_INICIAL, Globales, MODULOS_MENU } from "./modules";

function Shell() {
  const ruta = useHashRoute(MODULOS, MODULO_INICIAL.id);
  const modulo = MODULOS.find(m => m.id === ruta) || MODULO_INICIAL;
  const tituloRef = useRef(null);
  const primeraVez = useRef(true);
  const [visitados, setVisitados] = useState(() => new Set([modulo.id]));

  useEffect(() => {
    setVisitados(previos => previos.has(modulo.id) ? previos : new Set([...previos, modulo.id]));
  }, [modulo.id]);

  useEffect(() => {
    document.title = "LICING · " + modulo.titulo;
    if (primeraVez.current) { primeraVez.current = false; return; }
    tituloRef.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [modulo]);

  const { HeaderExtra } = modulo;
  return (
    <div className="app" data-module={modulo.id}>
      <Sidebar modulos={MODULOS_MENU} activo={modulo.id} />
      <main>
        <Topbar />
        <div className="content">
          <PageHeading ref={tituloRef} titulo={modulo.titulo} descripcion={modulo.descripcion} extra={HeaderExtra ? <HeaderExtra /> : null} />
          {/* Cargar cada módulo al abrirlo y conservar después sus formularios y filtros. */}
          {MODULOS.filter(({ id }) => id === modulo.id || visitados.has(id)).map(({ id, Page }) => (
            <section key={id} data-page={id} hidden={id !== modulo.id}><Page activo={id === modulo.id} /></section>
          ))}
          <Footer />
        </div>
      </main>
      <Globales />
    </div>
  );
}

function Gate() {
  const { estado } = useAuth();
  if (estado !== "listo") return <LoginScreen />;
  // Los datos se cargan solo con sesión válida.
  return <LicitacionesProvider><Shell /></LicitacionesProvider>;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider><Gate /></AuthProvider>
    </ThemeProvider>
  );
}

