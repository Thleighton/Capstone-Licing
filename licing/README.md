# LICING

Frontend React con un único backend FastAPI basado en LICING Core. El proyecto Supabase **Usuarios/Licitaciones** reúne Auth, perfiles y PostgreSQL para licitaciones. También se conserva PostgreSQL local como entorno de desarrollo.

El alojamiento de React y Core es **Vercel**: sigue **[la guía de despliegue](docs/VERCEL.md)**, que incluye la preparación de Supabase. Docker es opcional para desarrollo y pruebas locales; los Compose no forman parte de producción.

## Estructura

```text
licing/
├── frontend/                    # React + Vite y módulos existentes
├── backend/licing-core/
│   ├── app/
│   │   ├── main.py              # Única aplicación FastAPI
│   │   ├── auth.py              # Validación de sesión, perfil activo y roles
│   │   ├── api/                 # Configuración pública, consultas e ingesta
│   │   ├── models/              # Tablas existentes de Core
│   │   └── services/            # Descarga, normalización y persistencia de Core
│   ├── alembic/                 # Migraciones existentes
│   ├── tests/
│   └── docker-compose.yml      # Solo Core + PostgreSQL
├── api/index.py                 # Entrada de Core para Vercel o uvicorn
├── supabase/migrations/         # Solo usuarios y perfiles
└── docker-compose.yml          # React + Core + PostgreSQL
```

## Configuración

1. Crea `.env` dentro de `licing/`, si todavía no existe. Las variables se describen en el [README principal](../README.md#2-variables-de-entorno).
2. Completa `USUARIOS_URL` y `USUARIOS_ANON_KEY` del mismo proyecto Supabase Usuarios/Licitaciones.
3. Completa `MP_TICKET` y `DATABASE_URL`. Puedes conservar estos valores en `backend/licing-core/.env`: ese archivo tiene prioridad sobre `licing/.env` y no se modifica al actualizar el código. Las variables del proceso tienen prioridad sobre ambos archivos.
4. La tabla `public.usuario`, sus políticas RLS y Supabase Auth se conservan. Sus migraciones están en `supabase/migrations/`.

El navegador recibe únicamente la configuración pública del proyecto para el login. Las credenciales de PostgreSQL y el ticket de Mercado Público permanecen en el servidor. Ya no se necesitan `SUPABASE_URL` ni `SUPABASE_SERVICE_ROLE_KEY` del backend retirado. `CRON_SECRET` es opcional y solo habilita la ingesta programada.

## Docker

Desde `licing/`:

```powershell
docker compose up --build
```

App: http://localhost:5173 · API: http://localhost:8000/api/docs

El Compose principal usa el mismo nombre de proyecto, contenedores y volumen predeterminado que el Compose original de Core (`licing-core`, `licing_db`, `licing_api` y `licing-core_licing_pgdata`). Si levantaste Core con un nombre de proyecto personalizado, usa el mismo `docker compose -p <nombre>` al pasar al Compose principal para reutilizar su volumen.

Ejecuta un solo Compose a la vez. Para cambiar desde el Compose de Core puedes detenerlo con `docker compose down` desde su carpeta, sin borrar volúmenes, y levantar el principal. Nunca uses `down -v` si quieres conservar sus datos.

La API aplica `alembic upgrade head` antes de arrancar. Se conservan los modelos y migraciones de almacenamiento de Core. Una migración adicional habilita RLS en sus tablas para compartir proyecto con Auth. El código se monta como volumen y se recarga al editarlo.

## Local sin Docker

Requiere Python 3.12, Node y un PostgreSQL accesible. Si PostgreSQL está en Docker, usa `localhost` en el `DATABASE_URL` local; dentro de Compose se utiliza `db`.

Desde `licing/`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
```

Desde `licing/backend/licing-core/`, con ese entorno activado:

```powershell
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

En otra terminal, desde `licing/frontend/`:

```powershell
npm ci
npm run dev
```

También puedes ejecutar `uvicorn api.index:app --reload --port 8000` desde `licing/`: sirve la misma aplicación Core.

## API y permisos

| Ruta | Uso | Acceso |
|---|---|---|
| GET /api/config | Configuración pública del login | Público |
| GET /health, /api/salud | Salud de la aplicación | Público |
| GET /api/licitaciones | Listado con q, region, solo_abiertas, limite y offset | Usuario activo |
| GET /api/licitaciones/{id} | Detalle e ítems normalizados | Usuario activo |
| GET /api/dashboard | Indicadores de toda la base y próximos cierres | Usuario activo |
| GET /api/compras-agiles | Compras Ágiles guardadas, con q, region, solo_abiertas, limite y offset; incluye su clasificación vigente | Usuario activo |
| GET /api/compras-agiles/resumen | Indicadores de Compra Ágil para el dashboard y su página | Usuario activo |
| GET /api/compras-agiles/{id} | Detalle y productos solicitados | Usuario activo |
| /api/compras-agiles/preseleccion... | Clasificación hotelera, evaluación y criterios de cada Compra Ágil | Usuario activo |
| GET /api/ingestas | Últimas ejecuciones, con su `fuente` | Usuario activo |
| /api/ingesta/licitaciones/... | Rutas originales de descarga y procesamiento de Core | Administrador |
| /api/ingesta/compras-agiles/... | Lote, estado de la sincronización y descarga por código | Administrador |
| GET o POST /api/cron/ingesta | Lote programado, con limite de 1 a 5 (predeterminado 1); suma un lote de Compra Ágil en paralelo | `Authorization: Bearer <CRON_SECRET>` |
| GET o POST /api/cron/compras-agiles | Solo el lote de Compra Ágil, con limite de 1 a 20 (predeterminado 20) | `Authorization: Bearer <CRON_SECRET>` |

Las rutas originales `/ingesta/...` siguen disponibles con los mismos permisos para compatibilidad. Envía el token de Supabase Usuarios/Licitaciones como `Authorization: Bearer <token>`. El frontend lo adjunta y renueva automáticamente.

Los administradores tienen un botón **Obtener licitaciones** que ejecuta un lote de un detalle. La ingesta conserva los límites, la pausa entre descargas y el bloqueo de Core.

La misma ingesta puede ejecutarse automáticamente desde un planificador externo, como [cron-job.org](https://cron-job.org/), que llama a `/api/cron/ingesta` cada 5 minutos. Vercel Cron no sirve para esa frecuencia en el plan Hobby, que lo limita a una ejecución diaria. Sin `CRON_SECRET` la ruta responde 503. Si otra ingesta sigue en curso, responde 200 con `omitida: true` y no descarga nada. Configuración en [docs/VERCEL.md](docs/VERCEL.md#8-ingesta-automática-cada-5-minutos).

Cada detalle del lote se procesa dentro de una transacción anidada. Si un ítem es inválido, se revierten la licitación y sus ítems, se conserva la respuesta original y se continúa con los siguientes códigos. El historial registra el resultado parcial y sus errores.

## Datos y pantallas

- **Licitaciones** (antes Oportunidades) reúne los indicadores, la descarga de Excel y la preselección con los tres pilares, clasificación y rango inclusivo de fechas de cierre (`cierre_desde`, `cierre_hasta`). No muestra filtros de región ni de solo abiertas. `#oportunidades` conserva compatibilidad y redirige a `#licitaciones`.
- Las fichas muestran código, organismo, estado, montos con su moneda, fechas e ítems de Core.
- Las fechas originales sin zona se interpretan como hora de Chile al responder; no se modifica el almacenamiento de Core.
- El dashboard conserva las alertas de próximos cierres y el asistente de demostración. Los indicadores y el Excel están en Licitaciones; los controles de preselección están en las páginas de Licitaciones y Compras Ágiles. Estar abierta no representa compatibilidad comercial.
- Las pantallas de perfil, disponibilidad, clientes, seguimiento y reportes conservan su demostración. El análisis de bases utiliza ejemplos locales, sin depender del backend retirado.
- El contexto de la API y las categorías de los ítems se conservan para futuras búsquedas. Véase [DATOS_NORMALIZADOS.md](docs/DATOS_NORMALIZADOS.md).
- Se pueden registrar versiones de documentos, texto y hechos extraídos mediante la API. No se almacenan PDF ni se ejecuta extracción o IA automáticamente.
- La ingesta de Compra Ágil usa la API v2 (`api2.mercadopublico.cl`) con el mismo `MP_TICKET`. Cada lote las preselecciona con el mismo motor que las licitaciones y guarda el resultado en LicitacionesFiltradas. Datos, límites y orden de despliegue en [DATOS_NORMALIZADOS.md](docs/DATOS_NORMALIZADOS.md#ingesta-de-compra-ágil).
- La página **Compras Ágiles** comparte los tres pilares y controles de clasificación y fechas con las licitaciones. **Todas** consulta las compras guardadas en Core, incluso si aún no tienen una evaluación vigente. Al abrir la pantalla se comprueban las pendientes sin escribir; **Actualizar preselección** las reevalúa, también si el perfil activo de filtradas invalidó la marca local. Los administradores pueden adelantar un lote desde **Obtener Compras Ágiles**. La corrección manual de su clasificación todavía no está disponible.
- Las reglas `ca-2` conservan la región del comprador como referencia administrativa: no confirman ni rechazan el lugar del servicio por ella. Excluyen bienes y gráfica identificados en todas las líneas si no hay contratación hotelera concreta, conservando paquetes mixtos y líneas desconocidas. Revisión y límites de la comprobación: [auditoría de Compra Ágil](docs/AUDITORIA_COMPRA_AGIL_2026-10-28.md).
- **Reportes** está desactivado temporalmente en el menú y las rutas.
- Los filtros comerciales o semánticos todavía no forman parte del Core actual.
- El lote de Core busca códigos nuevos. Actualizar periódicamente detalles de licitaciones ya guardadas queda pendiente.

Los datos anteriores de Supabase Datos no se migran automáticamente: el esquema de Core es distinto. El destino actual es el proyecto único Usuarios/Licitaciones; las tablas creadas manualmente deben verificarse antes de registrarlas en Alembic.

## Pruebas

Desde `licing/backend/licing-core/`, con las dependencias de desarrollo instaladas:

```powershell
python -m pytest -q
```

Sin `TEST_DATABASE_URL`, se ejecutan las pruebas de autenticación, permisos y normalización; las de PostgreSQL se omiten. Las pruebas nunca usan el `DATABASE_URL` de tus archivos `.env`.

Para integración, prepara un PostgreSQL separado con un nombre de base que contenga `test`. En esa terminal configura ambas variables con su URL:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://usuario:clave@localhost:55439/licing_test'
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:MP_TICKET = 'test'
python -m alembic upgrade head
python -m pytest -q
```

Desde `licing/frontend/`: `npm run build`.

## Vercel

La guía principal está en **[docs/VERCEL.md](docs/VERCEL.md)**. En el proyecto Vercel usa Root Directory `licing` y Framework Preset `Other`.

`api/index.py` importa Core y `vercel.json` empaqueta su código. Configura `DATABASE_URL` de un PostgreSQL accesible desde el despliegue, `MP_TICKET`, `USUARIOS_URL` y `USUARIOS_ANON_KEY`. Para la ingesta programada, añade también `CRON_SECRET`.

Aplica las migraciones de Core antes del despliegue, desde un entorno conectado a esa base. Mantén los lotes pequeños para respetar el límite de ejecución de la función. Vercel no inicia el PostgreSQL local de Docker.

