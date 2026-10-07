import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import { irA } from "../../core/router/useHashRoute";
import ActividadReciente from "./components/ActividadReciente";
import AsistenteIA from "./components/AsistenteIA";
import { PublicacionesSemana, ResultadoPrefiltro } from "./components/Graficos";
import Indicadores from "./components/Indicadores";
import ProximasACerrar from "./components/ProximasACerrar";
import Rubros from "./components/Rubros";

export default function DashboardPage() {
  const { rows, total, runs, status, error, abrirFicha, setQ, setFiltros } = useLicitaciones();
  const estado = status.kind; // "" cargando | ok | err

  const nuevaBusqueda = () => {
    setQ(""); setFiltros({ tipo: "", soloValidas: false });
    irA("oportunidades");
    setTimeout(() => document.querySelector(".search input")?.focus(), 0);
  };
  const aplicarFiltros = () => { setFiltros({ visibles: true }); irA("oportunidades"); };

  return (
    <>
      <div className="home-actions" aria-label="Acciones principales">
        <a href="#formulario" aria-label="Completar el formulario del perfil del hotel"><span aria-hidden="true">✎</span>Completar perfil</a>
        <button onClick={nuevaBusqueda}><span>＋</span>Nueva búsqueda</button>
        <button onClick={aplicarFiltros}><span>≡</span>Aplicar filtros</button>
        <a href="#oportunidades"><span>↗</span>Ver resultados</a><a href="#disponibilidad"><span>▦</span>Disponibilidad</a>
        <a href="#clientes"><span>◎</span>Clientes</a><a href="#reportes"><span>▥</span>Reportes</a>
      </div>
      <div className="section-title live-heading"><h2>Indicadores y resultados consultados</h2><span className="badge">Datos de Supabase · independientes de la demostración</span></div>
      <div className="overview-note"><span className="badge blue">Panel de oportunidades</span><span>Indicadores sobre las últimas 500 licitaciones consultadas.</span></div>
      {error ? <div className="msg err">{error}</div> : estado === "ok" && <Indicadores rows={rows} total={total} />}

      <div className="dashboard-workspace">
        <div className="dashboard-main">
          <div className="chart-grid">
            <section className="card panel"><div className="section-title"><h2>Publicaciones de la semana</h2><span className="sub">Últimos 7 días · hora de Chile</span></div><PublicacionesSemana rows={rows} estado={estado} /></section>
            <section className="card panel"><h2>Resultado del pre-filtro</h2><ResultadoPrefiltro rows={rows} estado={estado} /></section>
          </div>
          <div className="grid">
            <section className="card panel"><div className="section-title"><h2>Próximas a cerrar</h2><a href="#oportunidades">Ver todas →</a></div>
              <ProximasACerrar rows={rows} estado={estado} abrirFicha={abrirFicha} /></section>
            <div className="side-col">
              <section className="card panel"><h2>Oportunidades por Rubro</h2>{estado === "ok" && <Rubros rows={rows} />}</section>
              <section className="card panel"><h2>Actividad Reciente</h2>{estado === "ok" && <ActividadReciente runs={runs} />}</section>
            </div>
          </div>
        </div>
        <AsistenteIA />
      </div>
    </>
  );
}
