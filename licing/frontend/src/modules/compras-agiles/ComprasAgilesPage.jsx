import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import Icon from "../../core/ui/Icon";
import VistaPreseleccion from "./components/VistaPreseleccion";
import { useActualizarComprasAgiles, useResumenComprasAgiles } from "./comun";
import { PilaresPreseleccion } from "../../core/ui/PreseleccionControles";
import UltimaBusqueda from "../../core/ui/UltimaBusqueda";
import DescargarOportunidades from "../dashboard/components/DescargarOportunidades";
import "../dashboard/dashboard.css";
import "./compras-agiles.css";

function Stat({ n, titulo, icono, nota, tono }) {
  return <div className={`stat stat-${tono}`}>
    <div className="top">{titulo}<span className="ico"><Icon name={icono} /></span></div>
    <div className="bottom"><b>{n ?? "–"}</b><small>{nota}</small></div>
  </div>;
}

export default function ComprasAgilesPage() {
  // Refrescar los datos compartidos recarga también esta página.
  const { actualizado } = useLicitaciones();
  const { versionDatos, actualizando, errorActualizacion, pendientes, avance, actualizar } = useActualizarComprasAgiles(actualizado);
  const { resumen, error } = useResumenComprasAgiles(versionDatos);
  return <div className="ca-page dashboard-page">
    <div className="section-title live-heading"><div><p className="dashboard-kicker">PANORAMA GENERAL</p><h2>Indicadores de Compras Ágiles</h2></div><span className="badge blue">Mercado Público · datos guardados</span></div>
    <p className="overview-note">Resumen general de las Compras Ágiles guardadas en Mercado Público.</p>
    {error && <div className="msg err" role="alert">No se pudo actualizar el resumen. {error}</div>}
    <section className="stats" aria-label="Indicadores de Compras Ágiles">
      <Stat n={resumen?.nuevas} titulo="Incorporadas hoy" icono="plus" nota="Últimas 24 horas" tono="violet" />
      <Stat n={resumen?.abiertas} titulo="Abiertas" icono="bolt" nota="Según el último detalle guardado" tono="teal" />
      <Stat n={resumen?.cierran_pronto} titulo="Cierran pronto" icono="clock" nota="En las próximas 24 horas" tono="amber" />
      <Stat n={resumen?.total} titulo="Guardadas" icono="briefcase" nota="Total de Compras Ágiles" tono="blue" />
    </section>
    <DescargarOportunidades endpoint="/api/compras-agiles/exportar.xlsx"
      nombreFallback="LICING-compras-agiles.xlsx" entidad="Compras Ágiles" />
    <section className="card preseleccion ca-opportunities">
      <div className="section-title pre-heading"><div className="pre-heading-title"><span className="pre-heading-icon"><Icon name="bolt" /></span><div><h2>Compras Ágiles para el hotel</h2><p className="sub">Considera salones para eventos y servicios de alimentación asociados. Se evalúan vigencia, ubicación en la RM y pertinencia.</p></div></div>
        <button className="primary" type="button" disabled={actualizando} onClick={actualizar}>{actualizando ? "Actualizando…" : "Actualizar preselección"}</button></div>
      <PilaresPreseleccion />
      <UltimaBusqueda fuente="compra_agil" />
      <p className="pre-nota" role="note">La lista puede incluir procesos abiertos y cerrados. La etiqueta junto al código indica si aún reciben cotizaciones.</p>
      {resumen && !resumen.carga_inicial_completa && <p className="ca-aviso" role="status"><Icon name="clock" />Carga inicial en curso: las Compras Ágiles abiertas se incorporan gradualmente.</p>}
      {pendientes > 0 && !actualizando && <p className="ca-aviso" role="status">Hay {pendientes} Compras Ágiles pendientes de evaluación. Usa “Actualizar preselección” para procesarlas.</p>}
      {actualizando && <p className="ca-aviso" role="status"><Icon name="clock" />Evaluando Compras Ágiles: {avance.evaluadas} procesadas, {avance.pendientes} pendientes.</p>}
      {errorActualizacion && <p className="msg err" role="alert">No se pudo actualizar la preselección. {errorActualizacion} Puedes volver a intentarlo con Actualizar preselección.</p>}
      <VistaPreseleccion version={versionDatos} actualizando={actualizando} />
    </section>
  </div>;
}
