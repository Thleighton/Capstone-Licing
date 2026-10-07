import { useLicitaciones } from "../data/LicitacionesProvider";

export default function Footer() {
  const { actualizado, rows, total, datosHost } = useLicitaciones();
  if (!actualizado) return <footer />;
  return (
    <footer>
      Origen: {datosHost || "Licing/Datos"} - actualizado {actualizado.toLocaleTimeString("es-CL")}
      {total > rows.length ? " - se muestran las " + rows.length + " más recientes de " + total : ""}
    </footer>
  );
}
