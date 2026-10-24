# Preselección del Hotel Plaza San Francisco

Usuarios/Licitaciones es la capa de entrada: conserva RAW, normalización y documentos originales en `licitacion_documento`, vinculados por `licitacion_id`. Los PDF están en el bucket privado `licitacion-bases` de **ese mismo proyecto**. El texto se conserva una sola vez, con índices que permiten reconstruir cada página; los filtros leen esa fuente.

LicitacionesFiltradas guarda oportunidades evaluadas, ítems, criterios, revisiones y referencias `documento_id/version/hash` en `evaluacion_filtro.entrada_evaluada`. No almacena PDF ni su texto completo. La migración `documentos_solo_en_origen` retira la tabla documental vacía y el control de descargas equivocados de filtradas; se detiene si encuentra documentos para evitar pérdida de datos. El bucket anterior queda deshabilitado para PDF.

La preselección considera vigencia, servicios hoteleros y lugar de ejecución en RM; no confunde domicilio del comprador con ejecución. Los casos desconocidos quedan para revisión. Todavía no ejecuta embeddings, ML o LLM ni decide postular. Los clientes estratégicos son una preferencia; las capacidades del hotel no se interpretan como disponibilidad.

## Instalación

1. Aplicar la migración Alembic de Core `b5df9fcc5f0d` en Usuarios/Licitaciones, después de `b8654f3a89fc`. Crea una sola tabla documental con eliminación en cascada al retirar la licitación y un campo de control de descargas en `licitacion`.
2. Aplicar `../docs/sql/documentos_storage_origen.sql` en **Usuarios/Licitaciones**: bucket privado, límite 3 MB y función de detección de huérfanos, exclusiva del servidor.
3. Desplegar `../backend/licing-core/supabase/functions/documentos-origen/index.ts` en **Usuarios/Licitaciones**. Tiene autenticación propia: valida el secreto existente mediante el callback fijo de Core, antes de leer el cuerpo. Usa las credenciales privilegiadas internas de ese proyecto. `DOCUMENTOS_STORAGE_URL` apunta a esta función; no hay claves en el navegador.
4. Aplicar en **LicitacionesFiltradas** las migraciones de `supabase/migrations` en orden. `001_base.sql` es un snapshot histórico para instalaciones nuevas; no repetirlo en la base existente. Desplegar allí la versión actual de `licing-filtradas`, que ya no permite operaciones documentales.
5. Para anexos Word y Excel: aplicar `../docs/sql/documentos_storage_anexos.sql` en **Usuarios/Licitaciones** (amplía los tipos admitidos del bucket) y volver a desplegar `documentos-origen`.
6. Publicar Core y frontend. El callback autenticador debe estar disponible en producción. Inicializar el perfil desde **Actualizar preselección**; la descarga documental es independiente y no necesita que exista ese perfil.

Ambas funciones verifican su autorización de integración antes de operar. Se despliegan con `verify_jwt=false` únicamente porque realizan esa verificación propia; no son accesos anónimos. Auth y roles siguen en el proyecto original.

## Descarga y documentos

**Estado del canal de descarga:** `MP_DESCARGA_PORTAL_HABILITADA=false` por defecto. La descarga del botón público está comprobada técnicamente, pero no se ha confirmado que automatizar ese formulario sea un mecanismo autorizado para este uso. Antes de habilitarla hay que confirmar con ChileCompra la vía documentada aplicable o contar con su autorización. Los términos vigentes de la API exigen los mecanismos descritos en su sitio y prohíben eludir sus límites. Esta configuración no es una certificación legal.

Mientras el canal esté pendiente, tanto el cron como el botón de obtención devuelven `canal_descarga_no_confirmado` sin consultar el portal ni reservar trabajos. La carga manual, el almacenamiento privado, la extracción y los filtros siguen disponibles. Las descargas que se incorporen por un canal oficial deberán respetar sus límites y controles; no se evaden CAPTCHA, restricciones o autenticación.

Fuentes consultadas: https://www.chilecompra.cl/api/ y https://www.chilecompra.cl/terminos-y-condiciones-de-uso/. La API OCDS se anuncia en https://datos-abiertos.chilecompra.cl/descargas/procesos-ocds, pero las comprobaciones realizadas no recuperaron documentos de las licitaciones consultadas. No se ha ejecutado la carga masiva de las 150.

El cron existente `/api/cron/ingesta` ejecuta en paralelo un turno documental con sesión propia y reserva de dos minutos. Incluye las licitaciones existentes y las nuevas. `DOCUMENTOS_AUTOMATICOS=false` desactiva este acompañamiento; `/api/cron/documentos` permite programarlo por separado usando el mismo secreto. `POST /api/preseleccion/documentos/obtener`, autenticado como usuario, adelanta un turno. No procesa 150 oportunidades en una sola petición.

Descarga el PDF principal del botón público **Descarga bases**, verificando el código mostrado en la ficha, las cookies y el formulario ASP.NET. Con `MP_DESCARGA_ANEXOS_HABILITADA=true` (por defecto `false`, y solo junto a la variable anterior) también descarga los anexos de **Antecedentes para incluir en la oferta** (`VerAntecedentes.aspx`), que el portal entrega sin desafío. Restringe cada salto al host oficial HTTPS y a esas dos rutas; rechaza HTML, desafíos, archivos mayores de 3 MB y redirecciones externas. Si una página muestra un CAPTCHA, el turno se detiene. No consulta **Archivos adjuntos** (`ViewAttachment.aspx`), protegido con reCAPTCHA, ni realiza OCR. Que los documentos públicos se hayan leído no confirma que estén todas las bases.

Los anexos se aceptan en PDF, Word y Excel. El texto de `.docx` y `.xlsx` se lee en un proceso aislado (cada hoja de Excel cuenta como una página); los `.doc` y `.xls` antiguos se conservan sin leer y pasan a revisión manual. Otros formatos, los archivos que superan 3 MB o el máximo de 10 documentos activos se omiten y quedan como incidencia de la licitación, sin perder lo ya guardado. Cada anexo se identifica por su categoría, nombre y fecha del portal: si no cambió, no se vuelve a descargar.

Cada turno procesa una licitación y empieza un archivo nuevo solo si quedan al menos 7 segundos del presupuesto. Si faltan archivos, la licitación queda en `pendiente_continuar` y otro turno la completa, después de las licitaciones que aún no se han intentado.

El lector admite hasta 120 páginas y 300.000 caracteres, en proceso aislado. La cobertura conserva páginas ilegibles para revisión. Repetir la huella no duplica archivos; una nueva versión automática retira de la evaluación la anterior automática y mantiene su original. La reserva se libera o vence sola. Los fallos temporales esperan una hora; desde el tercer intento o si no hay acceso público, 24 horas. Un éxito se revisa a los siete días y los cambios del RAW adelantan la consulta.

La descarga y persistencia se confirman en origen antes de intentar la evaluación. Si filtradas falla, el documento se conserva. El retiro manual también se confirma en origen. Cambiar documentos invalida la firma usada para la preselección, aunque el RAW siga siendo el mismo. Las revisiones de entradas sin cambios se conservan.

Los PDF corruptos, protegidos, sin texto legible o con lectura parcial conservan el original y un motivo orientativo. Las descargas vacías o que no entregan PDF registran la incidencia en `licitacion.ingesta_documental`, incluso si no se pudo guardar un archivo. Una oportunidad disponible con cualquiera de esas incidencias pasa a revisión manual y no se descarta automáticamente por los filtros. La vigencia conserva prioridad: esta protección no retiene licitaciones cerradas o vencidas.

El apartado **Pendientes por revisar** consulta `GET /api/preseleccion/pendientes-documentales` directamente en origen y muestra la razón aunque filtradas no esté disponible o no haya perfil/evaluación inicial. El detalle muestra los problemas por archivo. Retirar un documento excluye su incidencia de la revisión, sin borrar su original. Incorporar un reemplazo válido permite reevaluar; un documento legible no oculta otro que siga ilegible.

Si el cron de ingesta se mantiene detenido, se pueden completar los documentos de las licitaciones existentes ejecutando `/api/cron/documentos` por lotes independientes. No hace falta volver a consultar ni reinsertar sus RAW para empezar esa tarea. Después de la publicación hay que ejecutarla o programarla expresamente; el código por sí solo no enriquece las 150 licitaciones históricas.

La baja de una licitación elimina sus registros documentales por clave foránea. El cron documental solicita por la API de Storage la eliminación de binarios huérfanos tras una hora de margen; no borra directamente `storage.objects`. La purga de oportunidades filtradas conserva su ejecución cada minuto.

## Verificación

`npm ci && npm test` prueba migraciones y persistencia de filtradas, incluido el retiro del almacenamiento erróneo y la conservación de referencias. Las pruebas de Core verifican texto por página sin duplicarlo, reservas, deduplicación, firmas y eliminación en cascada. Las pruebas Deno cubren autenticación, rutas, huellas, bucket de origen y limpieza por API. La CI usa PostgreSQL 17 y compila el frontend.
