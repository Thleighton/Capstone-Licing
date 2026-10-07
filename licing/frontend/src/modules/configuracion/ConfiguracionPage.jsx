// Configuración TENTATIVA. Próximo paso: guardar en usuario_preferencia (Licing/Usuarios).
import { useState } from "react";
import { useTheme } from "../../core/ui/ThemeProvider";

export default function ConfiguracionPage() {
  const { dark } = useTheme();
  const [feedback, setFeedback] = useState("");
  return (
    <>
      <div className="notice"><strong>Configuración tentativa.</strong> Estos campos no modifican las conexiones ni la configuración del sistema.</div>
      <form className="module-grid" onSubmit={e => { e.preventDefault(); setFeedback("Simulación completada. No se guardaron cambios ni se activaron notificaciones."); }}>
        <section className="card panel"><h2>Perfil del hotel</h2>
          <div className="fields spaced">
            <label className="wide">Nombre comercial<input defaultValue="Hotel Plaza San Francisco" /></label>
            <label>Ciudad<input defaultValue="Santiago" /></label>
            <label>Área responsable<select><option>Eventos y ventas</option><option>Reservas</option></select></label>
            <label className="wide">Correo de notificaciones<input type="email" placeholder="licitaciones@hotel.cl" /></label>
          </div>
          <button type="submit" className="primary spaced">Simular guardado</button>
          <p role="status" className="sub">{feedback}</p>
        </section>
        <section className="card panel"><h2>Preferencias de trabajo</h2>
          <div className="setting-row"><div><strong>Apariencia</strong><p className="sub">Puedes cambiarla desde la barra superior.</p></div><span className="badge green">{dark ? "Modo oscuro" : "Modo claro"}</span></div>
          <label className="setting-row"><span>Resumen diario de oportunidades</span><input type="checkbox" defaultChecked /></label>
          <label className="setting-row"><span>Avisos de cierre próximo</span><input type="checkbox" defaultChecked /></label>
          <label className="field">Anticipación del aviso<select defaultValue="3 días antes"><option>3 días antes</option><option>5 días antes</option><option>7 días antes</option></select></label>
          <p className="sub">Las notificaciones se muestran como propuesta y todavía no se envían.</p>
        </section>
      </form>
    </>
  );
}
