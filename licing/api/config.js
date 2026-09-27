// Entrega al navegador la configuración pública para iniciar sesión en el proyecto
// Supabase "Licing/Usuarios" (.env en local, Settings > Environment Variables en Vercel).
// Solo expone la anon/publishable key de Usuarios. Los datos de "Licing/Datos" se leen
// a través de /api/datos, que verifica la sesión; el navegador no recibe keys de Datos.
module.exports = (req, res) => {
  let datosHost = "";
  try { datosHost = new URL(process.env.SUPABASE_URL).host; } catch (_) {}
  const cfg = {
    USUARIOS_URL: process.env.USUARIOS_URL || "",
    USUARIOS_KEY: process.env.USUARIOS_ANON_KEY || "",
    DATOS_HOST: datosHost,
  };
  res.setHeader("Content-Type", "application/javascript; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end("window.LICING_CONFIG = " + JSON.stringify(cfg) + ";\n");
};
