// Entrega al navegador la configuración pública de Supabase leída desde las
// variables de entorno (.env en local, Settings > Environment Variables en Vercel).
// Solo expone la anon/publishable key: nunca la service_role.
module.exports = (req, res) => {
  const cfg = {
    SUPABASE_URL: process.env.SUPABASE_URL || "",
    SUPABASE_KEY: process.env.SUPABASE_ANON_KEY || "",
  };
  res.setHeader("Content-Type", "application/javascript; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end("window.LICING_CONFIG = " + JSON.stringify(cfg) + ";\n");
};
