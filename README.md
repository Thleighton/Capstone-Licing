# LICING 🏨📑

**Asistente inteligente de Mercado Público para el Hotel Plaza San Francisco.**

> Encuentra a tiempo las licitaciones y Compras Ágiles de alojamiento, salones y alimentación que le sirven al hotel. LICING las descarga, las ordena, descarta las que no corresponden y deja al equipo comercial lo único que le toca hacer: decidir si postula.

[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF.svg)](https://vite.dev/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%7C%2017-4169E1.svg)](https://www.postgresql.org/)
[![Supabase](https://img.shields.io/badge/Supabase-Auth%20%7C%20DB%20%7C%20Storage-3ECF8E.svg)](https://supabase.com/)
[![Vercel](https://img.shields.io/badge/Vercel-Hosting-000000.svg)](https://vercel.com/)
[![CI](https://github.com/Thleighton/Capstone-Licing/actions/workflows/core-postgres.yml/badge.svg)](https://github.com/Thleighton/Capstone-Licing/actions/workflows/core-postgres.yml)

---

<a id="tabla-de-contenidos" name="tabla-de-contenidos"></a>
## 📋 Tabla de Contenidos

- [Descripción](#descripcion)
- [Objetivos](#objetivos)
- [Equipo](#equipo)
- [Metodología de Trabajo](#metodologia)
- [Arquitectura del Sistema](#arquitectura)
- [Características Principales](#caracteristicas-principales)
- [Dashboard & Visualización](#dashboard-visualizacion)
- [Preselección Inteligente](#preseleccion-inteligente)
- [Administración e Ingesta](#panel-admin)
- [API](#api)
- [Instalación y Ejecución](#instalacion-ejecucion)
- [Pruebas & Integración Continua](#pruebas)
- [Despliegue](#despliegue)
- [Stack Tecnológico](#stack-tecnologico)
- [Estructura del Repositorio](#estructura-proyecto)
- [Documentación Adicional](#documentacion)

---

<a id="descripcion" name="descripcion"></a>
## 📝 Descripción

**LICING** es una aplicación web que apoya al Encargado de Licitaciones del **Hotel Plaza San Francisco** (Santiago) en la búsqueda de oportunidades de negocio con el Estado.

Mercado Público publica a diario miles de procesos de compra. Solo unos pocos piden servicios que el hotel puede prestar, y revisarlos a mano consume horas y hace que algunas oportunidades se pierdan. LICING resuelve ese problema en cuatro pasos:

1. **Obtiene** licitaciones y Compras Ágiles desde las APIs oficiales de Mercado Público, por lotes y de forma programada.
2. **Normaliza y guarda** cada proceso con su respuesta original, sus ítems, montos, fechas en hora de Chile y el historial de cada ingesta.
3. **Preselecciona** los procesos con tres pilares (vigencia, lugar de prestación en la Región Metropolitana y servicio solicitado) y deja registrado el motivo y la evidencia de cada decisión.
4. **Presenta** los resultados en un dashboard con indicadores, próximos cierres y fichas de detalle.

LICING **no postula ni decide por el hotel**. Ordena y explica la información para que el equipo comercial resuelva si participa.

---

<a id="objetivos" name="objetivos"></a>
## 🎯 Objetivos

**Objetivo general:** desarrollar una aplicación web que obtenga y analice automáticamente oportunidades de Mercado Público y Compra Ágil según los criterios del Hotel Plaza San Francisco, para apoyar al Encargado de Licitaciones en su evaluación y seguimiento comercial.

**Objetivos específicos:**

1. Definir y mantener los requisitos, casos de uso y criterios de aceptación, con trazabilidad entre la necesidad del hotel y la solución.
2. Integrar la obtención automática de oportunidades desde Mercado Público y Compra Ágil.
3. Implementar el filtrado y la selección de oportunidades según los parámetros del hotel.
4. Extraer de las bases y TDR los servicios, fechas críticas, presupuesto y requisitos administrativos.
5. Implementar la revisión de admisibilidad, la evaluación presupuestaria, el seguimiento por estados, el tablero de control y los informes de gestión.
6. Verificar los requisitos funcionales y no funcionales con pruebas documentadas y entregar el sistema con documentación técnica y de uso.

---

<a id="equipo" name="equipo"></a>
## 👥 Equipo

Proyecto desarrollado para el **Hotel Plaza San Francisco** en la asignatura **Capstone (APT122)**, Duoc UC, sede Padre Alonso de Ovalle.

| Integrante | Responsabilidades en el proyecto |
| :--- | :--- |
| **Diego Sandoval** | Estudio de mercado; frontend de Oportunidades y Configuración; autenticación y plataforma (Vercel, Supabase, CI); API de consultas e ingesta de datos |
| **Miguel Mancilla** | Perfil del hotel y análisis documental: criterios, requisitos y endpoints de análisis de bases en Core |
| **Thomas Leighton** | Dashboard, seguimiento, reportes, disponibilidad de salones y clientes, incluidas sus futuras escrituras comerciales en Core |

---

<a id="metodologia" name="metodologia"></a>
## 🔄 Metodología de Trabajo

El proyecto sigue un enfoque **ágil, iterativo e incremental**, organizado con backlog, épicas, historias de usuario y **sprints**. En cada ciclo el equipo selecciona tareas, implementa un incremento, lo revisa contra los requisitos y registra ajustes e impedimentos. La planificación se apoya en una Carta Gantt y en una matriz RACI con los roles de coordinación, UX/UI, backend, IA/NLP, datos y QA.

| Actividad | Enfoque | Semanas |
| :--- | :--- | :--- |
| A1 · Alcance y estudio de mercado | Tema, contacto con el hotel, alternativas, requisitos y perfil de usuario | S3–S5 |
| A2 · Diseño y decisiones técnicas | Stack, arquitectura, modelo de datos, casos de uso y prototipos | S4–S6 |
| A3 · Obtención de oportunidades | Conexión con la API de Mercado Público y Compra Ágil | S6–S7 |
| A4 · Filtrado | Parámetros del hotel y selección de oportunidades relevantes | S8 |
| A5 · Interfaz de consulta | Vista de oportunidades y configuración de búsqueda | S9 |
| A6 · Análisis documental | Lectura de bases y TDR, extracción de datos clave | S9–S12 |
| A7 · Tablero de control | Embudo, totales por estado e indicadores | S11–S14 |
| A8 · Presupuesto y seguimiento | Umbrales, alertas, admisibilidad y estados comerciales | S12–S14 |
| A9 · Integración y reportería | Integración de módulos e informes de gestión | S14–S16 |
| A10 · Pruebas y ajustes | QA, registro de incidencias y correcciones | S15–S16 |
| A11 · Documentación | README, manual de usuario y documentación final | S15–S17 |

**Flujo de trabajo en el repositorio:**

- Ramas `feat/<modulo>-<descripcion>` y `fix/<modulo>-<descripcion>`, integradas a `main` mediante Pull Request.
- Cada PR describe el comportamiento final y su validación. La CI de GitHub Actions ejecuta pruebas y compilación antes de integrar.
- Los cambios de esquema se versionan con migraciones Alembic. Las reglas de colaboración están en [CONTRIBUTING.md](licing/CONTRIBUTING.md).

---

<a id="arquitectura" name="arquitectura"></a>
## 🏗️ Arquitectura del Sistema

LICING se organiza en tres capas, con **un único backend** (LICING Core) que concentra toda la lógica de negocio:

```mermaid
graph TD
    subgraph Cliente ["Capa Cliente (React + Vite)"]
        Web["Aplicación web<br/>Dashboard, Oportunidades, Compras Ágiles, Clientes"]
    end
    subgraph Servidor ["Capa de Servidor (Python + FastAPI)"]
        Core["LICING Core<br/>Consultas, ingesta, preselección"]
        Cron["Planificador externo<br/>/api/cron/* cada 5 min"]
    end
    subgraph Integracion ["Capa de Integración"]
        Auth["Supabase Auth<br/>Sesión y roles"]
        MP["API Mercado Público<br/>Licitaciones + Compra Ágil v2"]
        Fil["Edge Function<br/>licing-filtradas"]
        DocFn["Edge Function<br/>documentos-origen"]
    end
    subgraph Datos ["Capa de Datos"]
        DB[("PostgreSQL<br/>Usuarios/Licitaciones")]
        DBF[("PostgreSQL<br/>LicitacionesFiltradas")]
        ST[("Supabase Storage<br/>licitacion-bases")]
    end

    Web --> Auth
    Web -- "/api/* + token" --> Core
    Cron -- "CRON_SECRET" --> Core
    Core --> Auth
    Core --> MP
    Core --> DB
    Core --> Fil
    Fil --> DBF
    Core --> DocFn
    DocFn --> ST
```

- **Capa Cliente**: aplicación de una página organizada por módulos (`licing/frontend/src/modules`). Cada módulo se registra en `modules/index.jsx` y puede activarse o pausarse en `habilitados.js`. Todas las llamadas usan `apiFetch()`/`apiJson()`, que adjuntan el token de Supabase y lo renuevan automáticamente.
- **Capa de Servidor**: **LICING Core** (`licing/backend/licing-core`) es una API FastAPI que valida la sesión, que la cuenta esté activa y el rol del usuario (`usuario_actual`, `solo_rol("administrador")`). Contiene la descarga desde Mercado Público, la normalización, la persistencia, la preselección y las consultas. En Vercel se publica como función Python mediante `licing/api/index.py`.
- **Capa de Integración**: Supabase Auth gestiona el login. La API de Mercado Público entrega licitaciones y la API v2 entrega Compras Ágiles con el mismo ticket. Dos Edge Functions (Deno/TypeScript) se encargan de guardar evaluaciones en LicitacionesFiltradas y documentos en Storage. Ambas validan su propia autorización.
- **Capa de Datos**:
  - **Usuarios/Licitaciones**: Auth, perfiles (`public.usuario` con RLS) y las tablas de Core: respuestas RAW, `licitacion`, `licitacion_item`, `licitacion_documento`, `compra_agil`, `compra_agil_item`, sincronizaciones e historial de ingestas.
  - **LicitacionesFiltradas**: oportunidades evaluadas, criterios, revisiones y referencias a los documentos usados.
  - **Storage `licitacion-bases`**: bucket privado con las bases y anexos (máx. 3 MB por archivo).
- **Seguridad**: el navegador solo recibe la configuración pública del login. La cadena de conexión, el ticket de Mercado Público y los secretos permanecen en el servidor.

El modelo de datos completo (lógico, relacional y diccionario de datos) está en [`licing/docs/modelo-datos/`](licing/docs/modelo-datos/).

---

<a id="caracteristicas-principales" name="caracteristicas-principales"></a>
## ✨ Características Principales

### 🔐 Autenticación y Roles
- Inicio de sesión con Supabase Auth; la sesión se renueva sola y se cierra al expirar.
- Perfiles en `public.usuario` con estado activo/inactivo y roles. Solo el rol `administrador` ejecuta ingestas.
- Core verifica cada petición: sin token válido o con la cuenta inactiva, la API rechaza el acceso.

### 📥 Ingesta de Licitaciones
- Descarga por lotes desde la API de Mercado Público, con pausa entre descargas y bloqueo para evitar ingestas simultáneas.
- Conserva la respuesta original (RAW) y genera registros normalizados: código, organismo, región, estado, montos con su moneda, fechas en hora de Chile e ítems.
- Cada licitación se procesa en una transacción anidada: si un ítem es inválido, se revierte esa licitación y el lote continúa con las demás.
- Historial de ejecuciones con resultado, cantidades y errores de cada lote.

### ⚡ Ingesta de Compra Ágil
- Descarga desde la API v2 (`api2.mercadopublico.cl`) con el mismo `MP_TICKET`.
- Sincronización por páginas y regiones configurables, con avance parcial entre lotes.
- Cada lote preselecciona las Compras Ágiles con el mismo motor que las licitaciones.

### 🔎 Licitaciones y Compras Ágiles
- Páginas independientes para **Licitaciones** y **Compras Ágiles**. El enlace anterior `#oportunidades` redirige a `#licitaciones`.
- Tres pilares compartidos con Compras Ágiles y controles de clasificación (posible oportunidad, revisión necesaria o todas) y fechas de cierre. La búsqueda y la paginación se resuelven en el servidor.
- Fichas con código, organismo, estado, montos, fechas, ítems o productos solicitados y el resultado de los tres pilares.

### 👥 Clientes *(demostración)*
- Listado de clientes con contacto y servicios de interés.
- Alta y baja de clientes demo, con validación de campos obligatorios, formato de correo y nombres duplicados.
- Distintivo de **cliente importante** en las licitaciones de organismos destacados.

### 📄 Documentos de Origen
- Registro de bases y anexos en PDF, Word (`.docx`) y Excel (`.xlsx`) en un bucket privado.
- Extracción de texto por página (hasta 120 páginas y 300.000 caracteres) en un proceso aislado; los archivos ilegibles pasan a revisión manual.
- Deduplicación por huella del archivo y control de versiones.
- La descarga automática desde el portal está **desactivada por defecto** (`MP_DESCARGA_PORTAL_HABILITADA=false`) hasta confirmar con ChileCompra un canal autorizado. LICING no evade CAPTCHA ni restricciones del portal.

### 🧩 Módulos en Pausa
Estas pantallas existen en el código, pero están ocultas en el menú hasta conectarlas con Core:
- **Perfil del hotel**: criterios y servicios que ofrece el hotel.
- **Salones del hotel**: disponibilidad y capacidad.
- **Bases y documentos**: análisis documental con ejemplos locales.
- **Seguimiento**: estados comerciales de cada oportunidad.
- **Reportes**: pausado temporalmente; se conservan su pantalla y código.

---

<a id="dashboard-visualizacion" name="dashboard-visualizacion"></a>
## 📊 Dashboard & Visualización

El dashboard es la pantalla de inicio y conserva la preselección de oportunidades, las alertas de cierre y el apoyo de trabajo:

- **Oportunidades para el hotel**: panel con pestañas de Licitaciones y Compras Ágiles y los tres pilares de preselección.
- **Próximas a cerrar**: alertas desde 4 días antes del cierre, con acceso directo a la ficha.
- **Asistente IA** *(demostración)*: recomendaciones de ejemplo, priorizadas en alta, media o baja, que muestran cómo se verá el motor de IA cuando esté disponible.

El bloque **Indicadores de licitaciones**, sus tarjetas de datos y la descarga de Excel están en **Licitaciones**. La preselección sigue disponible en el dashboard y en las páginas de **Licitaciones** y **Compras Ágiles**. Reportes sigue desactivado.

Estar abierta no significa que una oportunidad sea compatible con el hotel: esa clasificación la entrega la preselección.

---

<a id="preseleccion-inteligente" name="preseleccion-inteligente"></a>
## 🧠 Preselección Inteligente

El motor de preselección clasifica cada licitación y Compra Ágil con **tres pilares**, evaluados en este orden:

| Pilar | Pregunta | Ejemplo de descarte |
| :--- | :--- | :--- |
| 1. **Vigencia** | ¿El proceso sigue abierto? | Fecha de cierre vencida |
| 2. **Lugar de prestación** | ¿El servicio se presta en la Región Metropolitana? | Evento en otra región, aunque el comprador tenga domicilio en Santiago |
| 3. **Servicio solicitado** | ¿Pide alojamiento, salones, alimentación o una combinación? | Compra de mobiliario o material eléctrico |

- **Resultado**: si cumple los tres pilares, el proceso es una **posible oportunidad**. Un incumplimiento explícito lo **descarta**, y se muestra el primero según la jerarquía. Si falta un dato esencial, queda **pendiente de revisión manual**.
- **Trazabilidad**: cada pilar guarda su motivo y la evidencia que lo respalda (texto de la descripción, ítems o documentos).
- **Reglas explícitas**: no confunde el domicilio del comprador con el lugar del servicio ni una categoría genérica de producto con una contratación concreta. El catálogo de reglas está versionado en `app/data/preseleccion_hotel_v1.json`.
- **Recálculo**: cambiar la versión del motor o del catálogo invalida las evaluaciones anteriores. Las licitaciones se actualizan al abrir su página; en Compras Ágiles se comprueban las pendientes y se guardan con **Actualizar preselección**.
- **IA**: el filtrado semántico y el análisis con modelos de lenguaje se retiraron de esta versión y quedan como trabajo futuro. La preselección actual es determinista y explicable.

---

<a id="panel-admin" name="panel-admin"></a>
## ⚙️ Administración e Ingesta

Los usuarios con rol **administrador** operan la carga de datos desde la propia aplicación:

- Botón **Obtener licitaciones**, que ejecuta un lote de descarga respetando los límites y el bloqueo de Core.
- Historial de ingestas con fuente (licitación o Compra Ágil), resultado y errores.
- **Ingesta programada**: un planificador externo, como [cron-job.org](https://cron-job.org/), llama a `/api/cron/ingesta` cada 5 minutos. Esa ruta procesa un lote de licitaciones y, en paralelo, uno de Compra Ágil. Se usa un planificador externo porque Vercel Cron en el plan Hobby solo permite una ejecución diaria.
- Las rutas de cron exigen `Authorization: Bearer <CRON_SECRET>`. Sin el secreto responden 503, y si otra ingesta está en curso responden `omitida: true` sin descargar nada.

---

<a id="api" name="api"></a>
## 🔌 API

Documentación interactiva en `/api/docs` (Swagger) cuando el backend está en ejecución.

| Ruta | Uso | Acceso |
| :--- | :--- | :--- |
| `GET /api/config` | Configuración pública del login | Público |
| `GET /health`, `/api/salud` | Salud de la aplicación | Público |
| `GET /api/licitaciones` | Listado con `q`, `region`, `solo_abiertas`, `limite` y `offset` | Usuario activo |
| `GET /api/licitaciones/{id}` | Detalle e ítems normalizados | Usuario activo |
| `GET /api/dashboard` | Indicadores y próximos cierres | Usuario activo |
| `GET /api/compras-agiles` | Listado de Compras Ágiles con su clasificación | Usuario activo |
| `GET /api/compras-agiles/resumen` | Indicadores de Compra Ágil | Usuario activo |
| `GET /api/compras-agiles/{id}` | Detalle y productos solicitados | Usuario activo |
| `/api/preseleccion/...` | Clasificación, evaluación y pendientes documentales | Usuario activo |
| `GET /api/ingestas` | Últimas ejecuciones | Usuario activo |
| `/api/ingesta/licitaciones/...` | Descarga y procesamiento de licitaciones | Administrador |
| `/api/ingesta/compras-agiles/...` | Lote, estado y descarga por código | Administrador |
| `GET/POST /api/cron/ingesta` | Lote programado (licitaciones + Compra Ágil) | `CRON_SECRET` |
| `GET/POST /api/cron/compras-agiles` | Solo el lote de Compra Ágil | `CRON_SECRET` |

El detalle de parámetros y límites está en [licing/README.md](licing/README.md#api-y-permisos).

---

<a id="instalacion-ejecucion" name="instalacion-ejecucion"></a>
## 🚀 Instalación y Ejecución

### Requisitos

- Git
- **Con Docker (recomendado):** Docker Desktop
- **Sin Docker:** Python 3.12, Node.js y un PostgreSQL accesible
- Un proyecto Supabase con Auth y la tabla `public.usuario` (migraciones en `licing/supabase/migrations/`)
- Un ticket de la API de Mercado Público ([solicitud](https://api.mercadopublico.cl/))

### 1. Clonar el repositorio

```bash
git clone https://github.com/Thleighton/Capstone-Licing.git
```

```bash
cd Capstone-Licing/licing
```

### 2. Configurar variables de entorno

Crea `licing/.env` (o `licing/backend/licing-core/.env`, que tiene prioridad) con:

| Variable | Descripción | Obligatoria |
| :--- | :--- | :--- |
| `DATABASE_URL` | PostgreSQL de Core, p. ej. `postgresql+psycopg://licing:licing@localhost:5432/licing` | Sí |
| `MP_TICKET` | Ticket de la API de Mercado Público | Sí |
| `USUARIOS_URL` | URL del proyecto Supabase Usuarios/Licitaciones | Sí, para el login |
| `USUARIOS_ANON_KEY` | Clave pública (anon) de ese proyecto | Sí, para el login |
| `CRON_SECRET` | Secreto de las rutas `/api/cron/*` | Solo para ingesta programada |

Las demás opciones (tamaño de lotes, pausas, regiones de Compra Ágil, descarga documental) tienen valores por defecto en `licing/backend/licing-core/app/config.py`. Los archivos `.env` no se suben al repositorio.

### 3a. Ejecutar con Docker

Desde `licing/`:

```bash
docker compose up --build
```

| Servicio | URL |
| :--- | :--- |
| Aplicación web | http://localhost:5173 |
| API y documentación | http://localhost:8000/api/docs |
| PostgreSQL | `localhost:5432` (usuario, clave y base `licing`) |

La API aplica `alembic upgrade head` antes de arrancar y recarga el código al editarlo. Para detener sin perder datos usa `docker compose down`, nunca `down -v`.

### 3b. Ejecutar sin Docker

Backend, desde `licing/` (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
cd backend/licing-core
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend, en otra terminal desde `licing/frontend/`:

```bash
npm ci
```

```bash
npm run dev
```

### 4. Primer uso

1. Crea un usuario en Supabase Auth y su perfil activo en `public.usuario`, con rol `administrador` si va a ejecutar ingestas.
2. Inicia sesión en http://localhost:5173.
3. Pulsa **Obtener licitaciones** para descargar el primer lote, o programa `/api/cron/ingesta`.
4. Revisa el dashboard y pulsa **Actualizar preselección** para clasificar las oportunidades.

---

<a id="pruebas" name="pruebas"></a>
## 🧪 Pruebas & Integración Continua

**Backend**, desde `licing/backend/licing-core/`:

```bash
python -m pytest -q
```

- Sin `TEST_DATABASE_URL` se ejecutan las pruebas de autenticación, permisos, normalización y preselección; las de PostgreSQL se omiten.
- Para las pruebas de integración, usa una base separada cuyo nombre contenga `test`. Las pruebas nunca usan el `DATABASE_URL` de los archivos `.env` ([instrucciones](licing/README.md#pruebas)).
- La suite cubre ingesta, normalización, persistencia, preselección y sus pilares, Compra Ágil, cron, documentos, lectura de PDF y Office, ubicación y consultas.

**Frontend**, desde `licing/frontend/`:

```bash
npm run build
```

**CI**: [core-postgres.yml](.github/workflows/core-postgres.yml) se ejecuta en cada PR y en cada push a `main`. Aplica las migraciones y corre pytest sobre PostgreSQL 17, ejecuta las pruebas de `filtradas` y compila el frontend.

---

<a id="despliegue" name="despliegue"></a>
## ☁️ Despliegue

La aplicación se publica en **Vercel**:

- **Root Directory** `licing` y **Framework Preset** `Other`.
- El frontend se compila a `frontend/dist`; `api/index.py` expone Core como función Python en la región `gru1` (São Paulo), con 60 s de ejecución máxima.
- Variables en Vercel: `DATABASE_URL`, `MP_TICKET`, `USUARIOS_URL`, `USUARIOS_ANON_KEY` y, si corresponde, `CRON_SECRET`.
- Las migraciones de Alembic se aplican antes de cada despliegue que cambie el esquema.

Guía paso a paso, incluida la preparación de Supabase y la ingesta cada 5 minutos: [licing/docs/VERCEL.md](licing/docs/VERCEL.md).

---

<a id="stack-tecnologico" name="stack-tecnologico"></a>
## 🛠️ Stack Tecnológico

| Componente | Tecnología |
| :--- | :--- |
| **Frontend** | React 18, Vite 6, JavaScript, CSS |
| **Backend** | Python 3.12, FastAPI, Uvicorn, Pydantic Settings |
| **Cliente HTTP** | HTTPX (APIs de Mercado Público) |
| **Base de Datos** | PostgreSQL (Supabase en la nube; 16/17 en local y CI) |
| **ORM y Migraciones** | SQLAlchemy 2, Alembic |
| **Autenticación** | Supabase Auth, perfiles con RLS en `public.usuario` |
| **Almacenamiento de Archivos** | Supabase Storage (bucket privado `licitacion-bases`) |
| **Funciones Serverless** | Supabase Edge Functions (Deno/TypeScript) |
| **Procesamiento de Documentos** | pypdf, pypdfium2, lectura de `.docx`/`.xlsx` |
| **Hosting** | Vercel (sitio estático + función Python) |
| **Desarrollo Local** | Docker Compose |
| **Pruebas y CI** | pytest, pruebas Node/Deno, GitHub Actions |
| **Fuentes de Datos** | API de Mercado Público y API v2 de Compra Ágil |

---

<a id="estructura-proyecto" name="estructura-proyecto"></a>
## 📂 Estructura del Repositorio

```bash
Capstone-Licing/
├── .github/workflows/
│   └── core-postgres.yml        # CI: pytest + PostgreSQL 17, filtradas y build del frontend
├── FASE 1/                      # Evidencias grupales e individuales de la Fase 1
├── FINAL FASE 1/                # Entrega final de la Fase 1 y anexos
├── FASE 2/                      # Evidencias de la Fase 2
├── Fase 3/                      # Evidencias de la Fase 3
└── licing/                      # 🚀 Aplicación
    ├── frontend/                # React + Vite
    │   └── src/
    │       ├── core/            # API, autenticación, layout, router y UI compartida
    │       └── modules/         # dashboard, oportunidades, compras-agiles, clientes, reportes…
    ├── backend/licing-core/     # Backend único (FastAPI)
    │   ├── app/
    │   │   ├── main.py          # Aplicación FastAPI
    │   │   ├── auth.py          # Sesión, perfil activo y roles
    │   │   ├── api/             # Rutas: consultas, Compra Ágil, preselección, ingesta, cron
    │   │   ├── models/          # Modelos SQLAlchemy
    │   │   ├── services/        # Descarga, normalización, persistencia, preselección, documentos
    │   │   └── data/            # Catálogo versionado de la preselección
    │   ├── alembic/             # Migraciones de la base
    │   ├── supabase/functions/  # Edge Function documentos-origen
    │   └── tests/               # Pruebas pytest
    ├── api/index.py             # Entrada de Core para Vercel
    ├── filtradas/               # Migraciones y Edge Function de LicitacionesFiltradas
    ├── supabase/migrations/     # Usuarios y perfiles
    ├── docs/
    │   ├── modelo-datos/        # Modelo lógico, relacional y diccionario de datos
    │   ├── sql/                 # Scripts SQL de Storage y mantenimiento
    │   ├── VERCEL.md            # Guía de despliegue
    │   └── DATOS_NORMALIZADOS.md
    ├── docker-compose.yml       # React + Core + PostgreSQL en local
    └── vercel.json              # Configuración de Vercel
```

---

<a id="documentacion" name="documentacion"></a>
## 📚 Documentación Adicional

| Documento | Contenido |
| :--- | :--- |
| [licing/README.md](licing/README.md) | Guía técnica: configuración detallada, Docker, API y permisos |
| [licing/CONTRIBUTING.md](licing/CONTRIBUTING.md) | Reparto de trabajo, contratos entre frontend y backend, ramas y PR |
| [licing/docs/VERCEL.md](licing/docs/VERCEL.md) | Despliegue en Vercel + Supabase |
| [licing/docs/DATOS_NORMALIZADOS.md](licing/docs/DATOS_NORMALIZADOS.md) | Datos normalizados e ingesta de Compra Ágil |
| [licing/filtradas/README.md](licing/filtradas/README.md) | Preselección, LicitacionesFiltradas y documentos de origen |
| [licing/docs/modelo-datos/](licing/docs/modelo-datos/) | Modelo lógico, relacional y diccionario de datos |

---
*Desarrollado por el equipo LICING para el Hotel Plaza San Francisco · Capstone APT122, Duoc UC.*
