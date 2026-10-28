import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import Preseleccion from "../dashboard/components/Preseleccion";
import Indicadores from "../dashboard/components/Indicadores";
import DescargarOportunidades from "../dashboard/components/DescargarOportunidades";
import "../dashboard/dashboard.css";

export default function LicitacionesPage() {
  const { q, cargarResumen, dashboard, dashboardError, dashboardCargando } = useLicitaciones();
  return <div className="oportunidades-page">
    <div className="dashboard-page">
      <div className="section-title live-heading"><div><p className="dashboard-kicker">PANORAMA GENERAL</p><h2>Licitaciones</h2></div><span className="badge blue">Mercado Público · datos guardados</span></div>
      <p className="overview-note">Resumen general de las licitaciones guardadas en Mercado Público.</p>
      {dashboardError && <div className="msg err" role="alert">{dashboardError}{dashboard && " Se muestra el último resumen disponible."}</div>}
      {!dashboard && dashboardCargando && <p role="status">Cargando indicadores de licitaciones…</p>}
      {dashboard && <Indicadores resumen={dashboard} />}
      <DescargarOportunidades />
    </div>
    <Preseleccion onActualizada={cargarResumen} q={q} />
  </div>;
}

