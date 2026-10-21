import { useLicitaciones } from "../data/LicitacionesProvider";

export default function Footer() {
  const { actualizado, dashboard } = useLicitaciones();
  if (!actualizado) return <footer />;
  return (
    <footer>
      Licitaciones guardadas: {dashboard?.total ?? 0} · actualizado {actualizado.toLocaleTimeString("es-CL", { timeZone: "America/Santiago" })}
    </footer>
  );
}
