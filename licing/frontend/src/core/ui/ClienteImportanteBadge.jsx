import Icon from "./Icon";
import "./cliente-importante.css";

export default function ClienteImportanteBadge({ clientes = [], mostrarNombre = true }) {
  if (!clientes.length) return null;
  return <span className="important-client-badge" title={clientes.map(c => c.nombre).join(" · ")}>
    <Icon name="star" /><span>Cliente importante{mostrarNombre && <span className="important-client-name">{clientes.map(c => c.nombre).join(" · ")}</span>}</span>
  </span>;
}
