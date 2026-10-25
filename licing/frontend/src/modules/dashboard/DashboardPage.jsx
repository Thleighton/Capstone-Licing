import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import AsistenteIA from "./components/AsistenteIA";
import Indicadores from "./components/Indicadores";
import ProximasACerrar from "./components/ProximasACerrar";

import Preseleccion from "./components/Preseleccion";
import PanelComprasAgiles from "../compras-agiles/components/PanelDashboard";
import Icon from "../../core/ui/Icon";
import "./dashboard.css";

function PanelHeading({ icono, tono, titulo, nota, children }) {
  return <div className="section-title dashboard-panel-heading">
    <div className="panel-title"><span className={"panel-icon tone-" + tono}><Icon name={icono} /></span>
      <div><h2>{titulo}</h2>{nota && <p className="sub">{nota}</p>}</div>
    </div>{children}
  </div>;
}

export default function DashboardPage({ soloDashboard = false }) {
  const { dashboard, dashboardError, dashboardCargando, abrirFicha, cargarResumen, actualizado } = useLicitaciones();
  const estado = dashboard ? "ok" : dashboardCargando ? "" : "err";

  return (
    <div className="dashboard-page">
      <div className="section-title live-heading"><div><p className="dashboard-kicker">PANORAMA GENERAL</p><h2>Indicadores de licitaciones</h2></div><span className="badge blue">Mercado Público · datos guardados</span></div>
      <p className="overview-note">Resumen general de las licitaciones guardadas en Mercado Público.</p>
      {dashboardError && <div className="msg err" role="alert">{dashboardError}{dashboard && " Se muestra el último resumen disponible."}</div>}
      {dashboard && <Indicadores resumen={dashboard} />}

      <div className="dashboard-priorities">
        <Preseleccion onActualizada={cargarResumen} />
        <section className="card panel dashboard-panel panel-amber dashboard-deadlines"><PanelHeading icono="clock" tono="amber" titulo="Próximas a cerrar" nota="Alertas desde 4 días antes del cierre" />
          <ProximasACerrar rows={dashboard?.proximas || []} disponibles={dashboard?.proximas_disponibles !== false} estado={estado} abrirFicha={abrirFicha} mostrarFicha={!soloDashboard} /></section>
      </div>

      <PanelComprasAgiles version={actualizado} />

      <div className={"dashboard-workspace" + (soloDashboard ? " dashboard-only" : "")}>
        {!soloDashboard && <AsistenteIA />}
      </div>
    </div>
  );
}

