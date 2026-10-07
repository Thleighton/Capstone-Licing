import Icon from "../ui/Icon";
import { useLicitaciones } from "../data/LicitacionesProvider";

export default function Sidebar({ modulos, activo }) {
  const { status } = useLicitaciones();
  const textoBD = status.kind === "ok" ? "Base de datos conectada" : status.kind === "err" ? "Sin conexión" : "Conectando...";
  return (
    <aside>
      <div className="logo"><Icon name="logo" />LICING</div>
      <div className="hotel"><Icon name="hotel" />Plaza San Francisco</div>
      <nav aria-label="Módulos de Licing">
        {modulos.map(m => (
          <a key={m.id} href={"#" + m.id} className={m.id === activo ? "active" : undefined} aria-current={m.id === activo ? "page" : undefined}>
            <Icon name={m.icono} />{m.nav}
          </a>
        ))}
      </nav>
      <div className="side-foot"><span className={"dot " + status.kind} /><span>{textoBD}</span></div>
    </aside>
  );
}
