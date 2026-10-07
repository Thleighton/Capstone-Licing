# legacy/

Versión anterior de LICING (hasta el 06-10-2026), guardada solo como referencia mientras se termina la migración:

- `index.html` — prototipo monolítico (HTML + CSS + JS en un archivo). Su contenido ahora vive en `frontend/src/` repartido por módulos.
- `api/*.js` + `dev-server.js` — backend en Node. Portado a Python en `backend/licing/` (misma lógica y mismos endpoints).
- `vercel.json`, `.gitignore` — configuración anterior.

Cuando el equipo confirme que la nueva versión funciona en Vercel, esta carpeta se puede borrar.
