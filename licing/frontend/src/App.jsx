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
import { irA, useHashRoute } from "./core/router/useHashRoute";
import { ThemeProvider } from "./core/ui/ThemeProvider";
import ErrorBoundary from "./core/ui/ErrorBoundary";
import { MODULOS, MODULO_INICIAL, Globales, MODULOS_MENU } from "./modules";

function Shell() {
  const ruta = useHashRoute(MODULOS, MODULO_INICIAL.id);
  const modulo = MODULOS.find(m => m.id === ruta);
  const tituloRef = useRef(null);
  const primeraVez = useRef(true);
  const [visitados, setVisitados] = useState(() => new Set(modulo ? [modulo.id] : []));

  useEffect(() => {
    if (!modulo) return;
    setVisitados(previos => previos.has(modulo.id) ? previos : new Set([...previos, modulo.id]));
  }, [modulo]);

  useEffect(() => {
    document.title = "LICING · " + (modulo?.titulo || "Página no encontrada");
    if (primeraVez.current) { primeraVez.current = false; return; }
    tituloRef.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [modulo]);

  const HeaderExtra = modulo?.HeaderExtra;
  return (
    <div className="app" data-module={modulo?.id || "not-found"}>
      <Sidebar modulos={MODULOS_MENU} activo={modulo?.id} />
      <main>
        <Topbar />
        <div className="content">
          <PageHeading ref={tituloRef} titulo={modulo?.titulo || "Página no encontrada"} descripcion={modulo?.descripcion || "El enlace no corresponde a una sección de LICING."} extra={HeaderExtra ? <HeaderExtra /> : null} mostrarAccion={Boolean(modulo)} />
          {/* Cargar cada módulo al abrirlo y conservar después sus formularios y filtros. */}
          {modulo ? MODULOS.filter(({ id }) => id === modulo.id || visitados.has(id)).map(({ id, Page }) => (
            <section key={id} data-page={id} hidden={id !== modulo.id}><Page activo={id === modulo.id} /></section>
          )) : <section className="empty" role="status"><h2>No encontramos esa página</h2><p>Puede que el enlace esté incompleto o que la sección ya no esté disponible.</p><button className="primary" type="button" onClick={() => irA(MODULO_INICIAL.id)}>Ir al inicio</button></section>}
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
      <ErrorBoundary><AuthProvider><Gate /></AuthProvider></ErrorBoundary>
    </ThemeProvider>
  );
}

