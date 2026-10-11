# LICING — Asistente Inteligente de Mercado Público

Aplicación web para el equipo de eventos del Hotel Plaza San Francisco: obtiene licitaciones y compras ágiles de Mercado Público, las filtra, analiza sus bases y acompaña la decisión comercial.

- **Frontend:** React + Vite (`frontend/`), un módulo por carpeta.
- **Backend:** Python + FastAPI (`backend/licing/`), cumple RNF-03. Se publica en Vercel como función serverless (`api/index.py`).
- **Datos:** dos proyectos Supabase — *Licing/Usuarios* (login y perfiles) y *Licing/Datos* (licitaciones). El navegador nunca recibe la `service_role`.

Reparto de módulos y forma de trabajo: ver **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Estructura

```
licing/
├── api/index.py                  ← entrada del backend en Vercel (no tocar)
├── backend/
│   ├── licing/
│   │   ├── main.py               ← registra los routers de cada módulo
│   │   ├── core/                 ← auth, config, cliente Supabase (compartido)
│   │   └── modulos/
│   │       ├── config_publica.py ← GET /api/config
│   │       ├── datos.py          ← GET /api/datos (lectura segura de Licing/Datos)
│   │       ├── sync/             ← GET /api/sync (E1: Mercado Público → Supabase)
│   │       ├── analisis.py       ← /api/analisis/* (E4/E5)
│   │       └── plantilla.py      ← ejemplo para módulos nuevos
│   └── tests/                    ← pytest
├── frontend/
│   └── src/
│       ├── App.jsx               ← arma login + layout + módulos (no se toca para agregar módulos)
│       ├── core/                 ← auth, cliente API, layout, router, UI compartida
│       ├── shared/demo/          ← datos ficticios (salones, clientes, solicitudes)
│       ├── styles/global.css     ← estilos del prototipo original
│       └── modules/
│           ├── index.jsx         ← REGISTRO de módulos (orden del menú)
│           ├── _plantilla/       ← copiar para crear un módulo
│           ├── dashboard/  oportunidades/  perfil-hotel/  disponibilidad/
│           └── clientes/  analisis/  seguimiento/  reportes/  configuracion/
├── supabase/migrations/          ← SQL versionado
├── legacy/                       ← versión anterior (index.html + api Node), solo referencia
├── requirements.txt              ← dependencias Python (Vercel)
└── vercel.json
```

## Correr con Docker (recomendado)

Solo requiere **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** (no hace falta instalar Node ni Python).

1. Copia `.env.example` a `.env` (en la raíz) y completa las variables. Pide los valores por interno: nunca van al repo.
2. Desde la raíz del repo:
   ```bash
   docker compose up --build
   ```
3. Abrir http://localhost:5173 (app) · http://localhost:8000/api/docs (API).

El código se monta dentro de los contenedores: al guardar un archivo, el frontend y el backend se recargan solos. Comandos útiles:

```bash
docker compose down                                  # detener
docker compose up --build -V                         # tras cambiar package.json o requirements (reinstala dependencias)
docker compose exec -w /app/backend backend pytest   # pruebas del backend
docker compose logs -f backend                       # ver logs de un servicio
```

Si el puerto 5173 u 8000 ya está ocupado (por ejemplo, otro `npm run dev` abierto), ciérralo antes de levantar Docker.

## Correr en local (sin Docker)

Requisitos: **Node 20+** y **Python 3.11+**.

1. Copia `.env.example` a `.env` (en la raíz) y completa las variables. Si ya tenías `.env`, sirve el mismo.
2. Backend (terminal 1, desde la raíz):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
   pip install -r backend/requirements-dev.txt
   uvicorn api.index:app --reload --port 8000
   ```
   Documentación interactiva de la API: http://localhost:8000/api/docs
3. Frontend (terminal 2):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Abrir http://localhost:5173 — Vite reenvía `/api/*` al backend del puerto 8000.

Sincronizar a mano (con el backend corriendo):
```bash
curl -H "Authorization: Bearer $CRON_SECRET" "http://localhost:8000/api/sync?fuente=compra_agil"
```

## Pruebas

```bash
cd backend && pytest          # backend
cd frontend && npm run build  # verifica que el frontend compile
```

## Despliegue (Vercel)

`vercel.json` ya define: build del frontend (`frontend/dist`), la función Python `api/index.py` con todas las rutas `/api/*`, y el cron diario de `/api/sync` (11:00 UTC). Las variables de entorno son las mismas de `.env.example` (Settings → Environment Variables).

> Antes del primer deploy con esta estructura, en Vercel → Settings → General deja **Root Directory vacío** y **Framework Preset = Other** (vercel.json manda).
