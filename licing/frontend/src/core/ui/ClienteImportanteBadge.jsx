import { clientesDestacados } from "../data/clientes";
import { useLicitaciones } from "../data/LicitacionesProvider";
import Icon from "./Icon";
import "./cliente-importante.css";

export default function ClienteImportanteBadge({ oportunidad, clientes, mostrarNombre = true }) {
  const { clientesDemo } = useLicitaciones();
  const destacados = clientesDestacados(oportunidad, clientesDemo, clientes);
  if (!destacados.length) return null;
  const nombres = destacados.map(c => c.nombre).join(" · ");
  return <span className="important-client-badge" title={nombres}>
    <Icon name="star" /><span>Cliente importante{mostrarNombre && <span className="important-client-name">{nombres}</span>}</span>
  </span>;
}
