# Cómo trabajamos en LICING

## Reparto de módulos (propuesta)

Cada persona es **dueña** de sus carpetas: las revisa, decide su diseño y aprueba los PR que las tocan. Repartido por épicas (E1–E8) para equilibrar carga y complejidad.

| Responsable | Frontend (`frontend/src/modules/`) | Backend (`backend/licing/modulos/`) | Épicas |
|---|---|---|---|
| **Diego Sandoval** | `oportunidades/`, `configuracion/` + todo `core/` | `sync/`, `datos.py`, `config_publica.py` + `core/` | E1 Obtención de oportunidades · E3 Validación de ID · plataforma (login, layout, deploy) |
| **Miguel Mancilla** | `perfil-hotel/`, `analisis/` | `analisis.py`, *nuevos:* `criterios.py`, `nlp/` | E2 Búsqueda y filtrado semántico · E4 Análisis de bases/TDR con IA · E5 Admisibilidad |
| **Thomas Leighton** | `dashboard/`, `seguimiento/`, `reportes/`, `disponibilidad/`, `clientes/` | *nuevos:* `seguimiento.py`, `presupuesto.py`, `reportes.py` | E6 Evaluación presupuestaria · E7 Embudo y tablero · E8 Reportería |

Zonas compartidas (`core/`, `shared/`, `styles/global.css`, `main.py`, `modules/index.jsx`): se pueden cambiar, pero por PR y avisando en el grupo, porque afectan a todos.

### Qué sigue en cada módulo

Hoy varios módulos muestran **datos de ejemplo** (llevan un aviso en pantalla). El trabajo es reemplazarlos por datos reales:

- **Diego** — validar ID contra Mercado Público al abrir la ficha (E3); estado de la última sincronización y botón "Sincronizar ahora" para administradores; guardar preferencias en `usuario_preferencia`.
- **Miguel** — guardar el Perfil del hotel en `criterio_busqueda` (`POST /api/criterios`) para que `sync` use esas palabras; carga de PDF y extracción real en `/api/analisis` (hoy `/api/analisis/simular` devuelve un resultado fijo con la misma forma).
- **Thomas** — leer `salon`, `disponibilidad_salon` y `cliente_conocido` en vez de `shared/demo/hotel.js`; estados reales del embudo por licitación; umbrales presupuestarios; reportes con datos reales.

## Crear un módulo nuevo

**Frontend**
1. Copia `frontend/src/modules/_plantilla/` con el nombre del módulo.
2. Edita su `index.js` (`id`, `nav`, `titulo`, `responsable`, `epicas`…).
3. Regístralo en `frontend/src/modules/index.jsx` (el orden de la lista es el orden del menú).

**Backend**
1. Copia `backend/licing/modulos/plantilla.py`, cambia el `prefix` (`/api/<modulo>`).
2. Agrega su `router` a la lista `ROUTERS` de `backend/licing/main.py`.
3. Protege cada ruta con `Depends(usuario_actual)` (o `Depends(solo_rol("administrador"))`).

## Reglas del código

- **Llamadas al backend:** siempre con `apiFetch()` o `datos()` de `core/api/client.js`. Ya agregan el token, lo renuevan y vuelven al login si la sesión expiró. Nunca `fetch` directo a Supabase desde un módulo.
- **Leer una tabla nueva de Licing/Datos:** agrégala a `TABLAS` en `backend/licing/modulos/datos.py`. Para escribir, crea un endpoint en tu módulo backend (el navegador no escribe directo).
- **Datos compartidos entre módulos:** `useLicitaciones()` (licitaciones cargadas, búsqueda, `abrirFicha(id)`), `useAuth()` (perfil del usuario) o un store de `core/store/createStore.js`.
- **Secretos:** nunca en el frontend ni en el repo. Solo en `.env` (local) y en Vercel.
- **Errores del backend:** lanza `ErrorApi(status, "mensaje en español")`; el frontend lo muestra tal cual.
- **Pruebas:** cada endpoint nuevo con al menos un test en `backend/tests/`.

## Ramas y PR

1. Rama desde `main`: `feat/<modulo>-<descripcion>` (ej. `feat/analisis-carga-pdf`) o `fix/<modulo>-<descripcion>`.
2. Commits pequeños, en español, que digan qué cambia.
3. Antes del PR: `cd backend && pytest` y `cd frontend && npm run build` sin errores.
4. PR a `main` con captura si cambia la pantalla. Lo aprueba el dueño del módulo (y Diego si toca `core/`).
5. Vercel crea un deploy de vista previa por cada PR: revisarlo antes de hacer merge.
