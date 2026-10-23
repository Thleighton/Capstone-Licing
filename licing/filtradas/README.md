# Preselección del Hotel Plaza San Francisco

Core conserva la ingesta y el RAW completos en Usuarios/Licitaciones. El segundo proyecto guarda las oportunidades evaluadas, ítems, resultados explicables, revisiones y documentos. No se crean tablas adicionales: se reutilizan las ocho existentes.

La preselección usa fecha y estado, ubicación del servicio (no domicilio del comprador), un catálogo amplio de servicios y reglas para ambigüedades. Los datos desconocidos van a revisión. No ejecuta embeddings, ML, LLM ni decide postular. Los clientes estratégicos son una preferencia, no una exclusión. Las capacidades del PDF del hotel se conservan en el perfil; no se suman salas combinadas ni se presupone disponibilidad.

## Documentos

El dashboard acepta PDF de hasta 3 MB, 120 páginas y 10 documentos activos por oportunidad. Core lee un máximo de 300.000 caracteres por documento en un proceso con límites de memoria y tiempo. El PDF original se conserva en Storage privado; el texto conserva página y evidencia. Un lector alternativo intenta recuperar PDF mal estructurados. No hay OCR: páginas escaneadas o ilegibles fuerzan revisión. La lectura de un archivo no confirma que se hayan recibido todas las bases. No se descargan anexos automáticamente: la API de Mercado Público no entrega un conjunto completo de enlaces.

Retirar un PDF invalida la evaluación y conserva el archivo para trazabilidad hasta la eliminación de la oportunidad. Repetir un archivo idéntico lo reutiliza. Repetir una evaluación idéntica conserva la revisión humana; cambios de fuente, perfil o documentos invalidan los resultados anteriores. Los descartes por falta de capacidad no se etiquetan automáticamente como ejemplos negativos del rubro.

## Instalación

1. En un proyecto nuevo, ejecutar `001_base.sql` una sola vez. **La base del usuario ya tiene ese esquema: no repetirlo.**
2. Aplicar las migraciones de `supabase/migrations` únicamente en LicitacionesFiltradas, en orden. La primera es portable y se prueba automáticamente; la segunda configura Storage privado y una purga cada minuto.
3. Desplegar `supabase/functions/licing-filtradas/index.ts` con `verify_jwt=false`. La función valida **cada solicitud** contra el endpoint fijo de Core antes de leer el cuerpo; no es una función anónima. Usa las variables privilegiadas internas de Supabase y nunca las devuelve al cliente.
4. Desplegar Core y frontend. `FILTRADAS_URL` apunta a la función. `CRON_SECRET` debe existir en Core; se reutiliza la credencial privada del planificador, no se solicita ni guarda una clave del segundo proyecto en el navegador. El callback apunta exclusivamente al dominio de producción.
5. Un usuario activo pulsa **Actualizar preselección** para registrar el perfil versionado y evaluar los datos existentes. El cron de ingesta evalúa después cada nuevo lote; si filtradas no responde, conserva la ingesta y señala que hay evaluación pendiente.

La limpieza de filtradas elimina vencidas/cerradas y sus dependencias cada minuto. Al actualizar la preselección o procesar una ingesta, sincroniza las bajas de la fuente original usando una lectura completa, con protección para altas posteriores al snapshot. Los binarios huérfanos se retiran mediante la API de Storage en evaluaciones posteriores, tras una hora de margen; no se borran directamente filas de `storage.objects`. No hay almacenamiento ilimitado: controlar el uso de Database y Storage; adjuntar bases solo a oportunidades potenciales o dudosas.

## Verificación

`npm ci && npm test` en esta carpeta valida migraciones, ítems repetidos, idempotencia, revisión, cambios concurrentes, permisos y eliminación física. `npx deno test supabase/functions/licing-filtradas/handler_test.ts` verifica autenticación y límites del adaptador. Core tiene pruebas de reglas, evidencias, PDF y API; la CI ejecuta su suite en PostgreSQL 17 y compila el frontend.

La subida y revisión no requieren modificar el dashboard existente ni reactivar módulos retirados. Para revertir la interfaz y Core, revertir el commit de aplicación; las migraciones son aditivas salvo el cambio de unicidad de los ítems y no requieren borrado para desactivar el panel.
