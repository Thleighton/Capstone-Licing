import { useLicitaciones } from "../../core/data/LicitacionesProvider";
import Preseleccion from "../dashboard/components/Preseleccion";
export default function OportunidadesPage() {
  const { q, cargarResumen } = useLicitaciones();
  return <div className="oportunidades-page">
    <Preseleccion onActualizada={cargarResumen} mostrarModalidades={false} q={q} />
  </div>;
}

