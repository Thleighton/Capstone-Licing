import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import { irA } from "../../core/router/useHashRoute";
import ActividadReciente from "./components/ActividadReciente";
import AsistenteIA from "./components/AsistenteIA";
import { PublicacionesSemana, EstadoVigencia } from "./components/Graficos";
import Indicadores from "./components/Indicadores";
import ProximasACerrar from "./components/ProximasACerrar";
import Estados from "./components/Estados";

export default function DashboardPage({ soloDashboard = false }) {
  const { dashboard, runs, status, error, abrirFicha, setQ, setFiltros } = useLicitaciones();
  const estado = status.kind; // "" cargando | ok | err

  const nuevaBusqueda = () => {
    setQ(""); setFiltros({ region: "", soloAbiertas: false });
    irA("oportunidades");
    setTimeout(() => document.querySelector(".search input")?.focus(), 0);
  };
  const aplicarFiltros = () => { setFiltros({ visibles: true }); irA("oportunidades"); };

  return (
    <>
      {!soloDashboard && <div className="home-actions" aria-label="Acciones principales">
        <a href="#formulario" aria-label="Completar el formulario del perfil del hotel"><span aria-hidden="true">✎</span>Completar perfil</a>
        <button onClick={nuevaBusqueda}><span>＋</span>Nueva búsqueda</button>
        <button onClick={aplicarFiltros}><span>≡</span>Aplicar filtros</button>
        <a href="#oportunidades"><span>↗</span>Ver resultados</a><a href="#disponibilidad"><span>▦</span>Disponibilidad</a>
        <a href="#clientes"><span>◎</span>Clientes</a><a href="#reportes"><span>▥</span>Reportes</a>
      </div>}
      <div className="section-title live-heading"><h2>Indicadores de licitaciones</h2><span className="badge">{soloDashboard ? "Datos guardados" : "Datos guardados · independientes de la demostración"}</span></div>
      <div className="overview-note"><span className="badge blue">Panel de oportunidades</span><span>Indicadores sobre todas las licitaciones guardadas. La compatibilidad comercial está pendiente de evaluar.</span></div>
      {error ? <div className="msg err">{error}</div> : estado === "ok" && dashboard && <Indicadores resumen={dashboard} />}

      <div className={"dashboard-workspace" + (soloDashboard ? " dashboard-only" : "")}>
        <div className="dashboard-main">
          <div className="chart-grid">
            <section className="card panel"><div className="section-title"><h2>Publicaciones de la semana</h2><span className="sub">Últimos 7 días · hora de Chile</span></div><PublicacionesSemana datos={dashboard?.publicaciones || []} estado={estado} /></section>
            <section className="card panel"><h2>Vigencia de las licitaciones</h2><EstadoVigencia resumen={dashboard} estado={estado} /></section>
          </div>
          <div className="grid">
            <section className="card panel"><div className="section-title"><h2>Próximas a cerrar</h2>{!soloDashboard && <a href="#oportunidades">Ver todas →</a>}</div>
              <ProximasACerrar rows={dashboard?.proximas || []} estado={estado} abrirFicha={abrirFicha} mostrarFicha={!soloDashboard} /></section>
            <div className="side-col">
              <section className="card panel"><h2>Estados en Mercado Público</h2>{estado === "ok" && <Estados datos={dashboard?.estados || []} />}</section>
              <section className="card panel"><h2>Actividad Reciente</h2>{estado === "ok" && <ActividadReciente runs={runs} />}</section>
            </div>
          </div>
        </div>
        {!soloDashboard && <AsistenteIA />}
      </div>
    </>
  );
}

