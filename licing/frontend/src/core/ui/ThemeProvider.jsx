// Modo claro / oscuro. El valor inicial lo pone el script de index.html.
import { createContext, useContext, useEffect, useState } from "react";

const Ctx = createContext(null);
export const useTheme = () => useContext(Ctx);

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => (document.documentElement.dataset.theme === "dark" ? "dark" : "light"));
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("licing-theme", theme); } catch (_) { /* sigue funcionando en esta pestaña */ }
  }, [theme]);
  const toggle = () => setTheme(t => (t === "dark" ? "light" : "dark"));
  return <Ctx.Provider value={{ theme, dark: theme === "dark", toggle }}>{children}</Ctx.Provider>;
}
