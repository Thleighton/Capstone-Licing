import "./titulo-licitacion.css";

export default function TituloLicitacion({ licitacion, as: Elemento = "h3", className = "", id }) {
  const organismo = licitacion?.nombre_organismo?.trim() || licitacion?.nombre_unidad?.trim();
  return <Elemento id={id} className={`licitacion-heading ${className}`}>
    <span className="licitacion-name" title={licitacion?.nombre}>{licitacion?.nombre || "Licitación sin título"}</span>
    <span className="licitacion-requester" title={licitacion?.nombre_unidad || organismo}>
      {organismo ? `Solicitante: ${organismo}` : "Solicitante no informado"}
    </span>
  </Elemento>;
}
