# Trabajo en LICING

## Backend único

Toda implementación de backend se hace en `backend/licing-core/app/`. Se mantienen los modelos, servicios de persistencia y migraciones de Core. El backend anterior de LICING se retiró.

- Diego: frontend de oportunidades/configuración, autenticación y plataforma; API de consultas y obtención de datos.
- Miguel: perfil del hotel y análisis documental. Los nuevos endpoints de criterios, requisitos e IA se agregan a Core.
- Thomas: dashboard, seguimiento, reportes, disponibilidad y clientes. Las futuras escrituras comerciales también se implementan en Core.

Los cambios compartidos se coordinan mediante PR. El registro del menú está en `frontend/src/modules/index.jsx`.

## Contratos

- El frontend usa `apiFetch()` o `apiJson()` de `core/api/client.js`. Agregan el token, lo renuevan y gestionan sesiones expiradas.
- Las lecturas pasan por las rutas de Core; no se usa el proxy PostgREST del backend anterior ni se consulta Supabase Datos.
- Los campos de licitación usan los nombres de Core, como `codigo_externo`, `estado` y `region_comprador`.
- Nuevas rutas privadas: `Depends(usuario_actual)`; escrituras administrativas: `Depends(solo_rol("administrador"))`, desde `app/auth.py`.
- Las credenciales y el ticket nunca se exponen al navegador.
- Los cambios de esquema se versionan en Alembic. El proyecto Supabase Usuarios/Licitaciones contiene Auth, perfiles y las tablas de Core; cada conjunto conserva sus migraciones.
- Mantén los avisos de demostración en módulos que todavía usen ejemplos.

## Comprobaciones

Agrega pruebas significativas para nuevas consultas, escrituras o reglas de negocio en `backend/licing-core/tests/`.

Ejecuta `python -m pytest -q` desde Core y `npm run build` desde el frontend. Las pruebas de PostgreSQL requieren una base separada mediante `TEST_DATABASE_URL`; consulta el README para prepararla.

Crea ramas `feat/<modulo>-<descripcion>` o `fix/<modulo>-<descripcion>` y PR con una descripción del comportamiento final y su validación.
