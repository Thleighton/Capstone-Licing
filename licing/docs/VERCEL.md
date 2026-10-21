# Publicar LICING en Vercel con una sola base Supabase

El alojamiento de la aplicación es **Vercel**. El proyecto **Supabase Usuarios/Licitaciones** contiene Auth, perfiles y las tablas de Core. Docker es una herramienta opcional de desarrollo o pruebas, no un componente del despliegue.

```mermaid
flowchart LR
  Navegador --> React[React en Vercel]
  React -->|/api y token| Core[Core en Vercel Functions Python]
  subgraph Supabase["Supabase: Usuarios/Licitaciones"]
    Auth[Auth y perfiles]
    Datos[(Licitaciones e ingestas)]
  end
  React -->|Login| Auth
  Core -->|Validar usuario| Auth
  Core -->|Consultar y guardar| Datos
  Core -->|Descargar| MP[Mercado Público]
```

## 1. Preparar el proyecto Supabase existente

Conserva las siete tablas de usuarios y Core que ya creaste. Mantén la Data API habilitada porque el login lee `public.usuario`. Las tablas de Core quedan protegidas con la migración RLS, y se consultan a través de FastAPI.

Obtén del mismo proyecto:

- La URL pública, por ejemplo `https://REF.supabase.co`.
- La clave pública de Auth, publishable o la anon que ya utilizabas.
- La conexión de PostgreSQL desde **Connect > Session pooler**, puerto **5432**.

Core utiliza un bloqueo de sesión para impedir ingestas simultáneas. Por eso esta versión conserva Session pooler en 5432. No la cambies al pooler de transacciones del puerto 6543 sin adaptar ese bloqueo. En Vercel, Core usa `NullPool` para cerrar las conexiones al devolverlas y delegar el pool en Supabase. [Conexiones de Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

## 2. Registrar las tablas manuales antes del despliegue

Este es un paso de preparación, no un servidor local permanente. Vercel no ejecuta migraciones al atender solicitudes ni al compilar React.

Puedes usar Python 3.12 sin Docker. Desde la carpeta del repositorio, prepara el entorno una vez:

```powershell
cd .\licing
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si `py -3.12` no está disponible, utiliza la ruta del ejecutable Python 3.12 instalado en tu equipo para crear el entorno.

Completa `licing/.env.supabase` con los datos del único proyecto. Si no existe, copia primero `.env.supabase.example`. Ese archivo está excluido de Git y del envío de archivos a Vercel.

Ejecuta la verificación de solo lectura:

```powershell
Push-Location .\backend\licing-core
..\..\.venv\Scripts\python.exe -m dotenv -f ..\..\.env.supabase run -- ..\..\.venv\Scripts\python.exe -m app.adopcion
Pop-Location
```

Si el esquema coincide, registra las tablas y aplica RLS:

```powershell
Push-Location .\backend\licing-core
..\..\.venv\Scripts\python.exe -m dotenv -f ..\..\.env.supabase run -- ..\..\.venv\Scripts\python.exe -m app.adopcion --registrar
Pop-Location
```

Si aparecen diferencias, revísalas antes de ejecutar `--registrar`. No borres las tablas para resolverlas ni uses `alembic stamp head` directamente. La adopción verificada conserva datos y perfiles.

No necesitas dejar ningún contenedor encendido para utilizar la aplicación publicada.

## 3. Configurar el proyecto de Vercel

Abre el proyecto Vercel conectado a este repositorio y verifica sus ajustes:

| Ajuste | Valor |
|---|---|
| Root Directory | `licing` |
| Framework Preset | `Other` |
| Install Command | `cd frontend && npm ci` |
| Build Command | `cd frontend && npm run build` |
| Output Directory | `frontend/dist` |

Los comandos y el directorio de salida ya están declarados en `licing/vercel.json`. No selecciones `frontend` como Root Directory: también deben estar disponibles `api/`, `requirements.txt` y `backend/licing-core/`.

La entrada `api/index.py` exporta la app FastAPI de Core. Vercel sirve el frontend compilado y dirige `/api/*` hacia esa función. `.python-version` fija Python 3.12. [Runtime Python de Vercel](https://vercel.com/docs/functions/runtimes/python).

## 4. Configurar Environment Variables en Vercel

En **Settings > Environment Variables**, configura:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres.REF:CLAVE_CODIFICADA@HOST:5432/postgres?sslmode=require
USUARIOS_URL=https://REF.supabase.co
USUARIOS_ANON_KEY=CLAVE_PUBLICA_DEL_MISMO_PROYECTO
MP_TICKET=TU_TICKET_REAL
MP_BASE_URL=https://api.mercadopublico.cl/servicios/v1/publico
MP_PAUSA_DETALLES_SEGUNDOS=5
MAX_RAW_ITEMS=20
```

Usa el mismo REF y el host copiado de Supabase Connect. Codifica los caracteres especiales de la contraseña dentro de la URL. El nombre visible Usuarios/Licitaciones no reemplaza al host ni al nombre PostgreSQL `postgres`.

Configura al menos el entorno **Production**. Si vas a probar un Preview, configura también sus variables y recuerda que usar el mismo `DATABASE_URL` implica utilizar la misma base real. La configuración del archivo local no se sube automáticamente al panel de Vercel.

Mantén habilitada la exposición de variables de sistema de Vercel para que el runtime reciba `VERCEL=1` y utilice el manejo de conexiones previsto para las funciones. [Variables de sistema](https://vercel.com/docs/environment-variables/system-environment-variables).

## 5. Desplegar

Publica el código mediante el flujo Git que uses en el proyecto o inicia un nuevo despliegue desde Vercel. Si acabas de cambiar variables, haz un **Redeploy** para que entren en vigor.

Comprueba el despliegue antes de probar la ingesta:

| Dirección | Resultado esperado |
|---|---|
| `https://TU-DOMINIO/` | Pantalla de login React |
| `https://TU-DOMINIO/api/salud` | Respuesta de salud de Core |
| `https://TU-DOMINIO/api/config` | URL y clave pública del login |
| `https://TU-DOMINIO/api/licitaciones` sin sesión | HTTP 401 |

La ruta de salud para Vercel es `/api/salud`, que atraviesa el rewrite declarado. Las credenciales de PostgreSQL y el ticket no aparecen en `/api/config`.

## 6. Configurar el login para el dominio publicado

En Supabase, abre **Authentication > URL Configuration**:

- Site URL: la URL HTTPS de la aplicación publicada.
- Redirect URLs: añade la dirección de retorno de esa aplicación para invitaciones y recuperación de contraseña.

Los perfiles deben existir en `public.usuario`, estar activos y tener el rol correcto. Para cargar nuevas licitaciones, la cuenta debe tener `rol = 'administrador'`. Conserva las políticas y triggers de usuarios que ya configuraste.

## 7. Cargar y mostrar licitaciones

Entra a la web publicada e inicia sesión. Pulsa **Obtener licitaciones**: React llama a la función de Core en Vercel, Core descarga y guarda en Supabase, y el frontend vuelve a consultar los datos.

El botón procesa como máximo un detalle por petición. `vercel.json` establece 60 segundos de duración máxima para la función: un lote pequeño reduce la posibilidad de superar ese límite, pero una respuesta lenta del proveedor todavía puede causar un timeout. [Duración de funciones](https://vercel.com/docs/functions/configuring-functions/duration).

Abre **Oportunidades**, una ficha y el dashboard. En Supabase puedes verificar las filas de `licitacion`, `licitacion_item` y `ejecucion_ingesta`.

No hay un cron de ingesta configurado en esta versión. **Actualizar** consulta la base; **Obtener licitaciones** descarga un detalle nuevo. Las pantallas de demostración conservan sus avisos.

## Papel de Docker

Los archivos Compose son herramientas locales opcionales. No forman parte del alojamiento en Vercel y no proporcionan una segunda base al despliegue. La aplicación publicada usa solamente el `DATABASE_URL` configurado en Vercel.
