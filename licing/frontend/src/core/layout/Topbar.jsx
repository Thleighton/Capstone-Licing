import Icon from "../ui/Icon";
import { irA } from "../router/useHashRoute";
import { useAuth } from "../auth/AuthProvider";
import { ROLES } from "../auth/session";
import { useLicitaciones } from "../data/LicitacionesProvider";
import { useTheme } from "../ui/ThemeProvider";

export default function Topbar({ soloDashboard = false }) {
  const { perfil, logout } = useAuth();
  const { q, setQ, status } = useLicitaciones();
  const { dark, toggle } = useTheme();
  const iniciales = (perfil?.nombre || "").split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("");

  return (
    <div className="topbar">
      {!soloDashboard && <label className="search"><Icon name="search" />
        <input type="search" placeholder="Buscar licitación, ID o institución..." value={q}
          onChange={e => { setQ(e.target.value); irA("licitaciones"); }} />
      </label>}
      <div className="spacer" />
      <div className={"status " + status.kind}><span className="dot" /><span>{status.text}</span></div>
      <button type="button" id="themeToggle" onClick={toggle} aria-pressed={dark} aria-label={dark ? "Activar modo claro" : "Activar modo oscuro"}>
        <span aria-hidden="true">{dark ? "☀" : "☾"}</span><span id="themeLabel">{dark ? "Modo claro" : "Modo oscuro"}</span>
      </button>
      {perfil && (
        <div className="user-chip">
          <span className="user-avatar" aria-hidden="true">{iniciales || "?"}</span>
          <span className="user-meta"><b title={perfil.email}>{perfil.nombre}</b><small>{ROLES[perfil.rol] || perfil.rol}</small></span>
          <button type="button" onClick={logout}>Salir</button>
        </div>
      )}
    </div>
  );
}

