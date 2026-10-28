import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import Icon from "../../core/ui/Icon";
import VistaPreseleccion from "./components/VistaPreseleccion";
import { useActualizarComprasAgiles, useResumenComprasAgiles } from "./comun";
import { PilaresPreseleccion } from "../../core/ui/PreseleccionControles";
import BotonIngesta from "../../core/layout/BotonIngesta";
import "./compras-agiles.css";

export function ObtenerComprasAgiles() {
  return <BotonIngesta fuente="compras-agiles" />;
}

function Stat({ n, titulo, icono, nota }) {
  return <div className="stat">
    <div className="top">{titulo}<span className="ico"><Icon name={icono} /></span></div>
    <div className="bottom"><b>{n ?? "–"}</b><small>{nota}</small></div>
  </div>;
}

export default function ComprasAgilesPage() {
  // Refrescar los datos compartidos recarga también esta página.
  const { actualizado } = useLicitaciones();
  const { versionDatos, actualizando, errorActualizacion, pendientes, actualizar } = useActualizarComprasAgiles(actualizado);
  const { resumen, error } = useResumenComprasAgiles(versionDatos);
  const pre = resumen?.preseleccion;
  return <div className="ca-page">
    <p className="overview-note">Compras Ágiles para el hotel, evaluadas con los mismos criterios que las licitaciones.</p>
    {error && <div className="msg err" role="alert">No se pudo actualizar el resumen. {error}</div>}
    {resumen && !resumen.carga_inicial_completa && <p className="ca-aviso" role="status"><Icon name="clock" />Carga inicial en curso: las Compras Ágiles abiertas se incorporan de a poco en cada turno.</p>}
    <section className="stats" aria-label="Indicadores de Compras Ágiles">
      <Stat n={resumen?.nuevas} titulo="Incorporadas hoy" icono="plus" nota="Últimas 24 horas" />
      <Stat n={resumen?.abiertas} titulo="Abiertas" icono="bolt" nota={resumen ? `${resumen.total} guardadas` : "Cargando…"} />
      <Stat n={resumen?.cierran_pronto} titulo="Cierran en 24 h" icono="clock" nota="Abiertas con cierre próximo" />
      <Stat n={pre?.preseleccionada} titulo="Posibles oportunidades" icono="star" nota={pre ? `${pre.revision_manual} en revisión` : "Cargando…"} />
    </section>
    <section className="card ca-opportunities">
      <div className="section-title"><h2>Compras Ágiles para el hotel</h2>
        <button className="primary" type="button" disabled={actualizando} onClick={actualizar}>{actualizando ? "Actualizando…" : "Actualizar preselección"}</button></div>
      <PilaresPreseleccion />
      {pendientes > 0 && !actualizando && <p className="ca-aviso" role="status">{pendientes} Compras Ágiles necesitan actualizar su evaluación. Pulsa Actualizar preselección para verlas con las reglas actuales.</p>}
      {errorActualizacion && <p className="msg err" role="alert">No se pudo actualizar la preselección. {errorActualizacion} Puedes volver a intentarlo con Actualizar preselección.</p>}
      <VistaPreseleccion version={versionDatos} actualizando={actualizando} />
    </section>
  </div>;
}
