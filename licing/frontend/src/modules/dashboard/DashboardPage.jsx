import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import AsistenteIA from "./components/AsistenteIA";
import ProximasACerrar from "./components/ProximasACerrar";
import Preseleccion from "./components/Preseleccion";
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
      {dashboardError && <div className="msg err" role="alert">{dashboardError}{dashboard && " Se muestra el último resumen disponible."}</div>}

      <div className="dashboard-priorities">
        <Preseleccion mostrarModalidades onActualizada={cargarResumen} versionComprasAgiles={actualizado} />
        <section className="card panel dashboard-panel panel-amber dashboard-deadlines"><PanelHeading icono="clock" tono="amber" titulo="Próximas a cerrar" nota="Alertas desde 4 días antes del cierre" />
          <ProximasACerrar rows={dashboard?.proximas || []} disponibles={dashboard?.proximas_disponibles !== false} estado={estado} abrirFicha={abrirFicha} mostrarFicha={!soloDashboard} /></section>
      </div>

      <div className={"dashboard-workspace" + (soloDashboard ? " dashboard-only" : "")}>
        {!soloDashboard && <AsistenteIA />}
      </div>
    </div>
  );
}

