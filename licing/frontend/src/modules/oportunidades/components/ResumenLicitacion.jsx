import { dinero, fecha } from "../../../core/ui/format";
import "./resumen-licitacion.css";

export default function ResumenLicitacion({ licitacion }) {
  const monto = licitacion.monto_estimado;
  const tieneMonto = monto != null && String(monto).trim() !== "" && Number.isFinite(Number(monto));
  const tituloMonto = { 1: "Presupuesto disponible", 2: "Precio referencial" }[licitacion.estimacion] || "Monto estimado";
  const publicado = licitacion.visibilidad_monto !== 0 && licitacion.estimacion !== 3 && tieneMonto;
  const valorMonto = licitacion.visibilidad_monto === 0 ? "No publicado"
    : licitacion.estimacion === 3 ? "No es posible estimar"
    : tieneMonto ? dinero(monto, licitacion.moneda) : "No informado";
  const descripcion = typeof licitacion.descripcion === "string" ? licitacion.descripcion.trim() : "";

  return <>
    {descripcion && descripcion !== licitacion.nombre?.trim() && <p className="pre-descripcion">{descripcion}</p>}
    <dl className="pre-resumen-licitacion" aria-label="Información de la licitación">
      <div className="pre-resumen-monto"><dt>{tituloMonto}</dt><dd data-publicado={publicado}>{valorMonto}</dd></div>
      <div><dt>Publicación</dt><dd>{licitacion.fecha_publicacion
        ? <time dateTime={licitacion.fecha_publicacion}>{fecha(licitacion.fecha_publicacion)}</time> : "No informada"}</dd></div>
      <div><dt>Cierre de ofertas</dt><dd>{licitacion.fecha_cierre
        ? <time dateTime={licitacion.fecha_cierre}>{fecha(licitacion.fecha_cierre)}</time> : "No informado"}</dd></div>
      <div><dt>Tipo de licitación</dt><dd>{licitacion.tipo || "No informado"}</dd></div>
      <div><dt>Estado del proceso</dt><dd>{licitacion.estado || "No informado"}</dd></div>
    </dl>
  </>;
}
