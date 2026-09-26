// Servidor local para desarrollo: sirve index.html y /api/sync (sin Vercel).
// Uso: copiar .env.example a .env, completar las variables y ejecutar `node dev-server.js`
const http = require("http");
const fs = require("fs");
const path = require("path");

try { process.loadEnvFile(path.join(__dirname, ".env")); }
catch { console.warn("Aviso: no se pudo leer .env (copia .env.example a .env y complétalo)"); }

const sync = require("./api/sync.js");
const config = require("./api/config.js");
const PORT = process.env.PORT || 3000;

http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/api/sync") {
    req.query = Object.fromEntries(url.searchParams);
    res.status = c => { res.statusCode = c; return res; };
    res.json = o => { res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify(o, null, 2)); };
    return sync(req, res);
  }
  if (url.pathname === "/api/config") return config(req, res);
  if (url.pathname === "/" || url.pathname === "/index.html") {
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    return res.end(fs.readFileSync(path.join(__dirname, "index.html")));
  }
  res.statusCode = 404; res.end("No encontrado");
}).listen(PORT, () => {
  console.log(`Dashboard:  http://localhost:${PORT}`);
  console.log(`Sincronizar: curl -H "Authorization: Bearer $CRON_SECRET" "http://localhost:${PORT}/api/sync?fuente=compra_agil"`);
});
