import { useEffect, useState } from "react";
import Icon from "./Icon";
import { fecha } from "./format";
import "./cierre-plazo.css";

function restante(fechaCierre, ahora) {
  if (!fechaCierre) return null;
  const ms = new Date(fechaCierre).getTime() - ahora;
  if (!Number.isFinite(ms)) return null;
  if (ms <= 0) return { texto: "Plazo vencido", nivel: "past" };
  if (ms <= 60 * 60 * 1000) {
    const minutos = Math.max(1, Math.ceil(ms / 60000));
    return { texto: `${minutos === 1 ? "Queda" : "Quedan"} ${minutos} min`, nivel: "critical" };
  }
  if (ms <= 24 * 60 * 60 * 1000) {
    const horas = Math.ceil(ms / 3600000);
    return { texto: `${horas === 1 ? "Queda" : "Quedan"} ${horas} h`, nivel: "critical" };
  }
  const dias = Math.floor(ms / 86400000);
  const horas = Math.floor((ms % 86400000) / 3600000);
  const textoDias = `${dias} ${dias === 1 ? "día" : "días"}`;
  const texto = horas ? `${textoDias} y ${horas} h` : textoDias;
  return { texto: `${dias === 1 ? "Queda" : "Quedan"} ${texto}`, nivel: dias < 4 ? "warning" : "normal" };
}

export default function CierrePlazo({ fechaCierre, compacto = false }) {
  const [ahora, setAhora] = useState(Date.now);
  useEffect(() => {
    const reloj = setInterval(() => setAhora(Date.now()), 60000);
    return () => clearInterval(reloj);
  }, []);

  const plazo = restante(fechaCierre, ahora);
  const fechaValida = fechaCierre && Number.isFinite(new Date(fechaCierre).getTime());
  return <div className={`cierre-plazo${compacto ? " cierre-plazo-compacto" : ""}`}>
    <time dateTime={fechaValida ? fechaCierre : undefined}>
      <span className="cierre-plazo-label">Cierre</span>
      <strong>{fechaValida ? fecha(fechaCierre) : "Sin fecha informada"}</strong>
    </time>
    {plazo && <span className="cierre-plazo-restante" data-nivel={plazo.nivel}>
      <Icon name="clock" />{plazo.texto}
    </span>}
  </div>;
}
